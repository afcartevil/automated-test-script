# Qualcomm msm-kernel DWC3 / Role / Gadget Reference

## 本树关键路径

- DWC3 Kconfig/Makefile：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/dwc3/Kconfig`
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/dwc3/Makefile`
- Qualcomm glue：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/dwc3/dwc3-msm-core.c`
- DRD/OTG：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/dwc3/drd.c`
- role switch 框架：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/roles/class.c`
- UDC 通用入口：
  - `vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/gadget/udc/core.c`

## 配置要点

- `USB_DWC3` + `USB_DWC3_DUAL_ROLE` 是 DRD 前提。
- `USB_DWC3_MSM` 启用 `dwc3-msm-core` glue。
- `USB_DWC3` 在 Kconfig 中会 select `USB_ROLE_SWITCH`（当 dual-role）。

## 角色切换链路（msm glue）

在 `dwc3-msm-core.c`：

1. `dwc3_msm_probe()`
   - 若 DTS 有 `usb-role-switch`，注册：
     - `dwc3_msm_usb_role_switch_set_role()`
     - `dwc3_msm_usb_role_switch_get_role()`
   - 若有 `extcon`，注册 VBUS/ID notifier。
2. role 切换入口
   - userspace/typec 请求 -> `dwc3_msm_usb_role_switch_set_role()`
   - 再到 `dwc3_msm_set_role()`
3. 具体执行
   - host: `dwc3_otg_start_host(on=1)`
   - device: `dwc3_otg_start_peripheral(on=1)`
4. 与 core DRD 对齐
   - 切换时会 `usb_role_switch_set_role(mdwc->dwc3_drd_sw, ...)`
   - OTG 模式会 `flush_work(&dwc->drd_work)` 同步时序

## OTG 事件链路（drd.c）

- `dwc3_otg_init()` 初始化 OTG 相关寄存器并设为 OTG port cap。
- `dwc3_otg_irq()` 读取 `DWC3_OEVT`，过滤 OTG 事件，必要时唤醒线程中断。
- `dwc3_otg_thread_irq()` 最终回到 `dwc3_set_mode(...OTG)` 并处理 host restart 场景。

## soft-connect 报错定位

`drivers/usb/gadget/udc/core.c`：

- `soft_connect_store()` 若 `!udc->driver`，直接报：
  - `soft-connect without a gadget driver`
- 说明 role 可能已经到 device，但 **UDC 未绑定 gadget function driver**（configfs/functions 未完成，或 gadget 驱动尚未 register/bind）。

可并行检查：
- `dwc3_otg_start_peripheral()` 中对 `dwc->gadget->udc->driver` 的判定与 `usb_gadget_connect()` 调用条件。

## 现象映射

| 现象 | 优先断点 |
|------|----------|
| role 写入成功但未切到 host/device | `dwc3_msm_usb_role_switch_set_role` -> `dwc3_msm_set_role` |
| 插线后仍不枚举 | `dwc3_resume_work` / `dwc3_otg_sm_work` / extcon notifier |
| device 模式报 soft-connect 错误 | `udc/core.c:soft_connect_store`，检查 UDC driver 绑定 |
| Host 模式偶发不起来 | `dwc3_otg_start_host` + `drd_work` flush + PM runtime 状态 |

## 与其他 skill 的边界

- UCSI/connector：`qualcomm-msm-kernel-usb-ucsi-analysis`
- usb/battery power_supply：`qualcomm-msm-kernel-charging-supply-analysis`
- glink BC/UC 交界：`qualcomm-kernel-adsp-bridge`
