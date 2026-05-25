---
name: qualcomm-msm-kernel-usb-ucsi-analysis
description: "Qualcomm-MSM-Kernel-UCSI: 基于msm-kernel drivers/usb/typec/ucsi分析UCSI，覆盖ucsi.c/ucsi_glink.c(pmic_glink)/psy/typec connector | UCSI/CCI/connector状态/命令超时/PPM | 当用户报告Qualcomm UCSI不同步、connector异常、UCSI命令超时时使用"
---

# Qualcomm msm-kernel UCSI 分析

## 适用范围

- 树路径（本仓库）：[`vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/)
- 覆盖 **通用 UCSI 核心**（`ucsi.c`）、**QTI PMIC Glink 传输**（`ucsi_glink.c`，`CONFIG_UCSI_QTI_GLINK`）、可选 **ACPI/CCG/STM32** 等其它后端（本机若未启用可略读）。
- **不包含**：`dwc3` 角色切换/枚举细节（见 `qualcomm-msm-kernel-dwc3-role-gadget-analysis`）、`qti_battery_charger` 内 USB 电源属性（见 `qualcomm-msm-kernel-charging-supply-analysis`）；与 ADSP 的 **glink owner 交界** 见 `qualcomm-kernel-adsp-bridge`。

## 模块边界

| 组件 | 职责 |
|------|------|
| `ucsi.c` + `ucsi.h` | UCSI 命令/状态机、`ucsi_register`、connector 管理 |
| `ucsi_glink.c` | `pmic_glink` 客户端 `MSG_OWNER_UC`，读写 UCSI 缓冲区、`UC_UCSI_USBC_NOTIFY_IND` |
| `psy.c` | 将 UCSI connector 映射为 **power_supply**（与 Intel 通用层同源，属性含 `USB_TYPE`/`ONLINE`/电压电流等） |
| `Makefile` + `Kconfig` | `typec_ucsi` 核心、`UCSI_QTI_GLINK` 编进 `ucsi_glink.o` |

## 固定入口（必须先读）

1. [`ucsi_glink.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/ucsi_glink.c)
   - `ucsi_callback()`：按 `opcode` 分派 read ack / write ack / **notify**
   - `handle_ucsi_notify()`：CCI → `ucsi_connector_change()`
   - `ucsi_qti_read()` / `ucsi_qti_glink_write()`：`pmic_glink_write()`
   - `ucsi_probe()`：`compatible = "qcom,ucsi-glink"`，`pmic_glink_register_client`
2. [`ucsi.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/ucsi.c)
   - `ucsi_create` / `ucsi_register` / connector 命令路径
3. [`psy.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/psy.c)
   - UCSI 侧 **power_supply** 与 connector 状态

## 分析步骤

```text
Qualcomm UCSI 排查清单
- [ ] 确认启用 UCSI_QTI_GLINK，且 pmic_glink 已 UP（ucsi_qti_state_cb）
- [ ] dmesg 查 UCSI: 与 notify/read/write 超时
- [ ] UC_UCSI_USBC_NOTIFY_IND 是否触发 handle_ucsi_notify
- [ ] CCI 解析后是否调用 ucsi_connector_change
- [ ] 与 BC 线混淆时：先分清是 connector（本 skill）还是 usb psy（charging-supply skill）
```

## 日志锚点

- `pr_fmt` 前缀：`UCSI:`
- `ucsi_log()` / `ucsi_dbg()`：CCI 与缓冲区十六进制（`notify:`、`read:`、`write:`）
- `register_ucsi_glink_notifier` / `ucsi_glink_notifier`：其它模块可挂 notifier（若平台使用）

## 转交

- **pmic_glink 双客户端、BC vs UC**：`qualcomm-kernel-adsp-bridge`
- **固件 LPM/DPM/PPM**：`qualcomm-adsp-usb-pd-analysis`
- **充电类型、RFC、ICM（ADSP）**：`qualcomm-adsp-charging-analysis`
- **qcom-battery / usb power_supply / Transsion glink**：`qualcomm-msm-kernel-charging-supply-analysis`
- **role switch / dwc3 / gadget 枚举**：`qualcomm-msm-kernel-dwc3-role-gadget-analysis`

## 附加资料

- opcode 与 Kconfig 细节见 [reference.md](reference.md)
