---
name: qualcomm-adsp-power-usb-triage
description: "Qualcomm-ADSP-Power/USB分诊: 在ADSP battman域内对Type-C/PD协议栈与充电识别(ICM)做首次分诊，路由到对应skill | dpm/pmic_glink/UCSI/TypeC/PD/充电 | 当用户报告Qualcomm平台USB/PD/充电跨模块问题时使用——本skill为路由入口"
---

# Qualcomm ADSP Power/USB 分诊（仅高通）

## 作用

在 **已确认是 Qualcomm ADSP battman 架构** 的前提下，先把问题归到两条深挖 skill 之一，避免在 `dpm` 两侧来回空转。

本 skill **不** 替代：
- `qualcomm-adsp-usb-pd-analysis`（LPM/TCPC/PPM/PD 语义）
- `qualcomm-adsp-charging-analysis`（APSD/QC/UFCS/RFC/ICM）

## 架构鸟瞰（固件内）

```text
PMIC PDPhy/Type-C IRQ
    -> TCPC state machine
    -> LPM (TCPM / PRL / PE)
    -> DPM (PwrMgr.PortStatus, 策略聚合)
         |-> PPM (UCSI/CCI) -> pmic_glink -> APSS
         |                    (kernel: ucsi_glink + qti_battery_charger)
         |
         +-> charger_detection / ssdev / tccharger / ICM
```

**交界锚点**：`dpm_handle_cable_event()` 同时服务「端口/PD 状态变化」与「向充电识别线程投递 TYPEC_UPDATE/CONTRACT_UPDATE」。从这里判断应往 **上** 追 LPM/ALERT，还是往 **下** 追 APSD/RFC/ICM。

## 分流规则（按现象）

1. **CC/附着、VBUS、SOP 收发、HardReset、Swap、PPS、UCSI/CCI、glink 通知异常**  
   → `qualcomm-adsp-usb-pd-analysis`  
   入口：`PmicTccPlatform_*IRQ` → `lpm_*` → `dpm_set_request_to_lpm` / `dpm_queue_lpm_async_event`。

2. **BC1.2/APSD 结果、SDP/CDP/DCP/FLOAT/QC、UFCS、RFC 握手、TFCP、charge pump、ICM 状态机**  
   → `qualcomm-adsp-charging-analysis`  
   入口：`charger_detection_*`、`ssdev_usb_*`、`tc_rfc_*`、`icm_core_*`。

3. **`dpm_handle_cable_event` 已执行，但充电类型仍错**  
   - 若 `PortStatus`/PD 合同看起来正常 → 先 **charging** skill（识别链）。  
   - 若 `PmReq` 卡在 `WAIT/FAIL` 或 `ConnectorStatus` 未更新 → 先 **usb-pd** skill。

4. **现象在 msm-kernel（固件已合理但 AP 不同步、psy/UCSI/sysfs）**  
   → 先 **`qualcomm-kernel-adsp-bridge`** 区分 **BC** 与 **UC** 客户端，再按现象进入：  
   - **`qualcomm-msm-kernel-usb-ucsi-analysis`**（connector/UCSI）  
   - **`qualcomm-msm-kernel-charging-supply-analysis`**（`qti_battery_charger`、Transsion）  
   - **`qualcomm-msm-kernel-dwc3-role-gadget-analysis`**（role switch、`dwc3`、gadget 枚举、`soft_connect`）

## 关键词速查

| 更偏 USB-PD skill | 更偏 Charging skill |
|-------------------|---------------------|
| `ALERT`, `tcpm_get_events_from_alert`, `USBPD_LPM_EVENT` | `APSD`, `usb_detect_partner`, `CHARGER_DETECTION_USB_UPDATE` |
| `PmReq`, `PM_REQUEST`, `GET_PPS_STATUS`, `DR_SWAP` | `QC`, `HVDCP`, `UFCS`, `RFC`, `TFCP`, `HL7139` |
| `PPM`, `CCI`, `ConnectorStatusChange`, `UCSI` | `icm_core`, `CHARGER_EVENT_CONTRACT_UPDATE`, `ICM` |
| `lpm_async_event_update`, `bAlertForwarding` | `slow` + `BC1.2`, `tc_rfc_detection` |

## 端到端时间线模板（仅 ADSP 视角）

```text
QCOM ADSP Timeline
- T0: 用户现象 / 日志锚点
- T1: TCPC/LPM：是否出现 ALERT 或 PM_REQUEST 完成？
- T2: DPM：PwrMgr.PortStatus 与 charger_detection_notify 是否触发？
- T3a: PPM/glink：CCI/Notify 是否到达 AP 侧预期？
- T3b: ssdev/tccharger：APSD/QC/RFC/ICM 是否进入预期支路？
```

## 输出模板

```markdown
## 平台
- Qualcomm ADSP battman（已确认）

## 首选深挖 skill
- <qualcomm-adsp-usb-pd-analysis | qualcomm-adsp-charging-analysis>

## 分流依据
- 现象与关键词：<...>
- 交界判断：<dpm 偏协议/通知 | dpm 偏充电识别/ICM>

## 建议入口
- 文件：<path>
- 函数：<function>

## 若需跨 skill
- 当前 skill 结论摘要：<1-3 行>
- 另一 skill 的起始检查点：<function>
```

## 约束

- 仅用于 **高通 ADSP**；不涉及 MediaTek 或其它平台术语混用。
- 分诊后必须进入对应 Qualcomm skill 按固定入口下钻，避免跳过 `dpm`/`charger_detection`/`lpm` 入口直接猜寄存器。

## 相关 skill

- `qualcomm-adsp-usb-pd-analysis`
- `qualcomm-adsp-charging-analysis`
- `qualcomm-kernel-adsp-bridge`
- `qualcomm-msm-kernel-usb-ucsi-analysis`
- `qualcomm-msm-kernel-charging-supply-analysis`
- `qualcomm-msm-kernel-dwc3-role-gadget-analysis`
