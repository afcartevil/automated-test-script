---
name: qualcomm-adsp-charging-analysis
description: "Qualcomm-ADSP-充电: 基于battman/battmngr/charger架构分析USB插入后充电识别与充电流程 | BC1.2/APSD/QC/HVDCP/UFCS/RFC/TFCP/charge_pump/DVCHG/HL7139A/ICM | 当用户报告Qualcomm平台充电慢、识别异常、DCP/QC分流错误、DPDM握手失败时使用"
funcType: "AI故障分析"
category: "驱动"
---

# Qualcomm ADSP Charging 分析

## 适用范围

聚焦 Qualcomm `ADSP` 侧 `battman/battmngr/charger` 架构，覆盖 USB 插入后到实际充电的识别与状态机流程。

**与 USB-PD skill 的分界**：本 skill 处理 `charger_detection` 之后、`ssdev`/`tccharger`/`ICM` 的识别与充电策略；`TCPC/LPM/PPM`、三条 PD 主线（ALERT/PM_REQUEST/ASYNC_EVENT）由 `qualcomm-adsp-usb-pd-analysis` 负责。二者通过 **`dpm_handle_cable_event()`** 与 **`charger_detection_notify()`** 交汇；跨域现象可先用 **`qualcomm-adsp-power-usb-triage`** 归位。

主路径：
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/battmngr/charger/main`
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/battmngr/charger/ssdev`
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/battmngr/charger/icm`
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/battmngr/charger/tccharger`
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/usbtypec/dpm`

包含：
- `DPM -> charger_detection / charger_thread` 桥接
- `BC1.2/APSD` 使能、rerun、slow detection
- `SDP/CDP/DCP/FLOAT/QC` 判定
- `QC/HVDCP` 与 `UFCS` 分流
- Transsion `RFC` 握手、`TFCP`、`DVCHG/HL7139A`
- `ICM` 状态机进入、重启、RFC 分支

不包含：
- `kernel` 侧 `dwc3/gadget/role switch`（深挖时转 `qualcomm-msm-kernel-charging-supply-analysis` / `qualcomm-msm-kernel-usb-ucsi-analysis` / `qualcomm-msm-kernel-dwc3-role-gadget-analysis`，交界见 `qualcomm-kernel-adsp-bridge`）
- Android framework / UsbService
- 纯 battery gauge 算法细节

## 日志与事件锚点（便于 grep）

优先在 ADSP 日志中检索（名称以实际固件字符串为准，下同）：

- `CHARGER_DETECTION_TYPEC_UPDATE`、`CHARGER_DETECTION_USB_UPDATE`、`CHARGER_DETECTION_USB_PLUGIN`
- `charger_detection_handle_charger_attach`、`charger_detection_handle_typec_charger_update`
- `usb_enable_apsd`、`usb_detect_partner`、`APSD`、`slow`
- `UFCS`、`QC`、`RFC`、`TFCP`、`tc_rfc`、`HL7139`、`icm_core`

## 固定入口

必须先从这几个入口开始：

1. `usbtypec/dpm/src/dpm.c`
   - `dpm_handle_cable_event()`
2. `charger/main/src/charger_detection.c`
   - `charger_detection_initial_detection()`
   - `charger_detection_handle_charger_attach()`
   - `charger_detection_handle_typec_charger_update()`
   - `charger_detection_event_handler()`
3. `charger/ssdev/src/ssdev_usb_7550b.c`
   - `usb_enable_apsd_detection()`
   - `usb_detect_partner()`
   - `usb_set_qc_voltage()`
4. `charger/icm/src/icm_core.c`
   - `icm_core_event_screening()`
5. `charger/tccharger/src/tc_rfc_ssdev.c`
   - `tc_rfc_detection_check()`
   - `rfc_handshake_by_cp_ic()`
   - `tc_rfc_enable_ta_charging()`
   - `rfc_stop_charging()`

## 主链路

```text
USB/Type-C IRQ
-> TCPC/LPM/DPM
-> dpm_handle_cable_event()
-> charger_detection_notify(TYPEC_UPDATE)
-> charger_detection_handle_*()

非 PD:
-> enable APSD
-> USB_UPDATE 读取 APSD result
-> 分流到 SDP/CDP/DCP/FLOAT/QC

DCP/legacy/PD failed:
-> UFCS / QC / RFC

RFC:
-> charge pump(DVCHG/HL7139A) 在 DP/DM 上握手
-> 打开 I2C 通信通道
-> TFCP 向 TA 下发电压电流
-> ICM 进入 RFC 充电分支
```

## 分析步骤

```text
Qualcomm ADSP Charging 排查清单
- [ ] 先确认入口是 TYPEC_UPDATE、USB_PLUGIN 还是 USB_UPDATE
- [ ] 先判定当前是 PD 还是 legacy/BC1.2 支路
- [ ] 检查 APSD 是否 enable、done、rerun
- [ ] 检查 UsbPartnerType 是否落到 SDP/CDP/DCP/FLOAT/QC
- [ ] 若是 DCP/legacy，检查是否继续进入 UFCS/QC/RFC
- [ ] 若是 RFC，检查 DP/DM 握手、I2C 通道开关、TFCP 通信
- [ ] 检查 charger_notify 是否触发 ICM 重启或转入 RFC 状态
```

## 分流规则

1. 命中 `APSD/BC1.2/SDP/CDP/DCP/FLOAT`
   - 优先看 `charger_detection` + `ssdev_usb_7550b`
2. 命中 `QC/HVDCP/QC2/QC3`
   - 优先看 `charger_detection_handle_typec_charger_update()` + `usb_set_qc_voltage()`
3. 命中 `RFC/tfcp/pca_tfcp_ta/protocol_ta/level shift`
   - 优先看 `tc_rfc_ssdev` + `tc_inf_class` + `tc_hl7139a`
4. 命中 `CONTRACT_UPDATE/CHGTYPE_CHANGE/ICM`
   - 优先看 `dpm_handle_cable_event()` + `icm_core_event_screening()`
5. 命中“慢插识别异常”
   - 优先看 `CHARGER_DETECTION_USB_UPDATE` 里的 `slow detection`

## 关键判断

- `PD active` 时应关闭 `APSD`
- `APSD result` 是 `DCP` 才有机会进入 `QC/RFC/UFCS` 深层分支
- `slow BC1.2` 是为了支持慢插场景下的 `BC1.2 + RFC` 识别
- `RFC` 不是抽象概念，实际落在 `DVCHG/HL7139A`
- `tc_smb_i2c_trans()` 是 RFC 通信通道开关
- `hl7139a_i2c_trans()` 通过写 `HL7139_REG19` 切换通信态
- RFC 成功后应切到 `SSDEV_PARTNER_TC_RFC`
- 后续应进入 `ICM` 的 RFC 充电分支，而不是停留在识别阶段

## 输出模板

```markdown
## 当前支路
- 主支路：PD / BC1.2 / QC / UFCS / RFC
- 入口函数：<function>

## 识别阶段
- APSD：enabled/done/rerun
- UsbPartnerType：<type>
- TypeC/PD 状态：<summary>

## RFC/QC 深层路径
- DPDM 握手：<ok/fail/not-applicable>
- I2C 通道：<enabled/disabled/not-applicable>
- TFCP/QC 调压：<state>

## ICM
- 触发事件：<event>
- 当前/下一状态：<state>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<file/function/register/log>
```

## 转交

- 现象横跨「PD 协议/通知」与「充电识别」、不确定先追哪条：`qualcomm-adsp-power-usb-triage`
- `USB PD/Type-C` 主问题：`qualcomm-adsp-usb-pd-analysis`
- **msm-kernel 充电与 psy**：`qualcomm-msm-kernel-charging-supply-analysis`（`qti_battery_charger`、`transsion/`）；**UCSI/CCI**：`qualcomm-msm-kernel-usb-ucsi-analysis`；**role/gadget 枚举**：`qualcomm-msm-kernel-dwc3-role-gadget-analysis`；**glink 双客户端交界**：`qualcomm-kernel-adsp-bridge`

## 附加资料

- 详细时间线、RFC 深层链路、HL7139A/TFCP 闭环见 [reference.md](reference.md)
