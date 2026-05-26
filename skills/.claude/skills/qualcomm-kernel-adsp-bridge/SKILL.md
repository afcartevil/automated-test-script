---
name: qualcomm-kernel-adsp-bridge
description: "Qualcomm-Kernel-ADSP桥: 描述msm-kernel上pmic_glink与ADSP固件的交界，双客户端(battery_charger/ucsi)与opcode对应关系 | pmic_glink/opcode/battery_charger/ucsi/ADSP固件/AP不同步 | 当用户报告Qualcomm固件更新后AP不同步，或需同时看UCSI与qti_battery_charger时使用"
funcType: "AI故障分析"
category: "驱动"
---

# Qualcomm Kernel ↔ ADSP（pmic_glink 交界）

## 适用范围

- **仅高通**：msm-kernel 中 `linux/soc/qcom/pmic_glink.h` 客户端与 **ADSP** `battman` 侧 `pmic_glink` 出口对齐。
- 本 skill **不** 深挖 `dwc3`/gadget 细节；该部分转 `qualcomm-msm-kernel-dwc3-role-gadget-analysis`。
- 本 skill 也 **不** 替代 `qualcomm-adsp-usb-pd-analysis` / `qualcomm-adsp-charging-analysis` 的固件内深挖。

## 双客户端（同一传输、不同 owner）

| Kernel 驱动 | `client_data.id`（MSG_OWNER） | `client_data.name` | 与 ADSP 侧语义 |
|---------------|-------------------------------|--------------------|----------------|
| [`qti_battery_charger.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/qti_battery_charger.c) | `32778`（`MSG_OWNER_BC`） | `battery_charger` | 电池/USB/无线充 **power_supply** 属性读写、`BC_NOTIFY_IND` 推送 |
| [`ucsi_glink.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/ucsi_glink.c) | `32779`（`MSG_OWNER_UC`） | `ucsi` | **UCSI** 读写缓冲区、`UC_UCSI_USBC_NOTIFY_IND`（CCI/async） |

固件侧 `PPM`/`battery charger` 服务分别与上述 **UC** / **BC** owner 对话；分析时 **不要** 把两条线的日志混成一条。

## 固定入口（kernel）

1. **BC**：`battery_chg_callback()` → `BC_NOTIFY_IND` → `handle_notification()`；否则 `handle_message()`（req/resp）。
2. **UC**：`ucsi_callback()` → `UC_UCSI_READ_BUF_REQ` / `UC_UCSI_WRITE_BUF_REQ` / `UC_UCSI_USBC_NOTIFY_IND`。

## 分析步骤

```text
pmic_glink 交界排查
- [ ] 确认问题需要 BC（充电类型/SOC/usb psy）还是 UC（UCSI/CCI/connector）
- [ ] dmesg 过滤 BATTERY_CHG: 与 UCSI:（pr_fmt 前缀）
- [ ] 核对 glink 是否 UP：battery_chg_state_cb / ucsi_qti_state_cb
- [ ] BC：notification 是否触发 power_supply_changed
- [ ] UC：UC_UCSI_USBC_NOTIFY_IND 是否到达且 ucsi_connector_change 执行
```

## 转交

- 固件内 **LPM/DPM/PPM**：`qualcomm-adsp-usb-pd-analysis`
- 固件内 **charger_detection / APSD / RFC / ICM**：`qualcomm-adsp-charging-analysis`
- **UCSI 实现与 typec 类**：`qualcomm-msm-kernel-usb-ucsi-analysis`
- **qti_battery_charger 与 Transsion glink**：`qualcomm-msm-kernel-charging-supply-analysis`
- **role 切换、dwc3、gadget 枚举/soft_connect**：`qualcomm-msm-kernel-dwc3-role-gadget-analysis`

## 附加资料

- 详细 opcode 与通知表见 [reference.md](reference.md)
