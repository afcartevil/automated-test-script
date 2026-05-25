---
name: qualcomm-msm-kernel-dwc3-role-gadget-analysis
description: "Qualcomm-MSM-Kernel-DWC3: 基于msm-kernel drivers/usb/dwc3/roles/gadget/udc分析DWC3 DRD/OTG角色切换与设备枚举 | dwc3/role_switch/Host/Device/gadget/UDC/soft_connect | 当用户报告Qualcomm DWC3角色错乱、Host/Device切换失败、gadget不枚举时使用"
---

# Qualcomm msm-kernel DWC3 / Role / Gadget 分析

## 适用范围

- DWC3 核心与 QTI MSM glue：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/dwc3/`
  - 重点：`dwc3-msm-core.c`、`drd.c`、`gadget.c`
- USB role switch 框架：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/roles/class.c`
- UDC 层（`soft_connect` / gadget 绑定）：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/gadget/udc/core.c`

不包含：
- UCSI/CCI 主线（转 `qualcomm-msm-kernel-usb-ucsi-analysis`）
- `qti_battery_charger` 充电属性主线（转 `qualcomm-msm-kernel-charging-supply-analysis`）

## 固定入口

1. `drivers/usb/dwc3/dwc3-msm-core.c`
   - `dwc3_msm_probe()`
   - `dwc3_msm_usb_role_switch_set_role()` / `dwc3_msm_set_role()`
   - `dwc3_otg_start_host()` / `dwc3_otg_start_peripheral()`
   - `dwc3_otg_sm_work()` / `dwc3_resume_work()`
   - `dwc3_msm_extcon_register()`、`dwc3_msm_vbus_notifier()`、`dwc3_msm_id_notifier()`
2. `drivers/usb/dwc3/drd.c`
   - `dwc3_otg_init()`
   - `dwc3_otg_irq()` / `dwc3_otg_thread_irq()`
3. `drivers/usb/roles/class.c`
   - `usb_role_switch_set_role()`
   - `usb_role_switch_get_role()`
4. `drivers/usb/gadget/udc/core.c`
   - `soft_connect_store()`（`soft-connect without a gadget driver`）

## 主链路（角色与枚举）

```text
Type-C/Extcon or userspace role request
-> dwc3_msm_usb_role_switch_set_role()
-> dwc3_msm_set_role()
-> dwc3_otg_start_host() or dwc3_otg_start_peripheral()
-> usb_role_switch_set_role(dwc3_drd_sw, HOST/DEVICE)
-> (device path) UDC bind + soft_connect + gadget connect
```

## 分析步骤

```text
DWC3/Role/Gadget 排查清单
- [ ] 先确定问题在 role 决策、还是 gadget 绑定/枚举阶段
- [ ] 看 dwc3_msm_probe 是否建立 role_switch 或 extcon 源
- [ ] 看 dwc3_msm_set_role 是否实际切到 HOST/DEVICE
- [ ] Device 模式检查 dwc3_otg_start_peripheral 与 usb_gadget_connect 调用
- [ ] 命中 "soft-connect without a gadget driver" 时，先查 UDC driver 绑定状态
- [ ] 若仅 UCSI connector 异常，改走 ucsi skill
```

## 日志锚点（建议 grep）

- `dwc3_msm_usb_role_switch_set_role`
- `dwc3_otg_start_host`
- `dwc3_otg_start_peripheral`
- `soft-connect without a gadget driver`
- `resume_work` / `otg_sm_work`

## 转交

- connector/CCI/UCSI 命令问题：`qualcomm-msm-kernel-usb-ucsi-analysis`
- 充电类型/usb psy/healthd 问题：`qualcomm-msm-kernel-charging-supply-analysis`
- ADSP 与 kernel glink 交界不清：`qualcomm-kernel-adsp-bridge`
- ADSP 固件层（LPM/DPM/PPM 或 APSD/RFC/ICM）：转对应 ADSP skill

## 附加资料

- 关键函数与状态映射见 [reference.md](reference.md)
