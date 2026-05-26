---
name: qualcomm-msm-kernel-charging-supply-analysis
description: "Qualcomm-MSM-Kernel-充电电源: 基于msm-kernel drivers/power/supply分析Qualcomm充电与电源，覆盖qti_battery_charger/pmic_glink/USB/BATT/WLS psy | psy/uevent/ICL/healthd/battery_charger | 当用户报告Qualcomm充电类型异常、psy uevent、healthd读失败时使用"
funcType: "AI故障分析"
category: "驱动"
---

# Qualcomm msm-kernel Charging / power_supply 分析

## 适用范围

- [`vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/qti_battery_charger.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/qti_battery_charger.c)：**高通原生** `pmic_glink` 电池充电客户端、`power_supply` 注册、`BC_NOTIFY_IND` 处理。
- [`vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/transsion/`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/transsion/)：**Transsion** 扩展（如 `tc_sys`、`wireless_manager`、`tc_water_detect` 等，随 `CONFIG_*` 编译）。
- [`vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/Makefile`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/Makefile)：`CONFIG_QTI_BATTERY_CHARGER`、`subdir-ccflags` 包含 `transsion/glink` 头路径、`obj-y += transsion/`（本树）。

**不包含**：UCSI/CCI 主线（见 `qualcomm-msm-kernel-usb-ucsi-analysis`）；DWC3 role/gadget 枚举（见 `qualcomm-msm-kernel-dwc3-role-gadget-analysis`）；ADSP 固件内 LPM（见 ADSP skill）。

## 固定入口

1. **`qti_battery_charger.c`**
   - `battery_chg_probe()`：`pmic_glink_register_client`，`MSG_OWNER_BC`，`compatible = "qcom,battery-charger"`
   - `battery_chg_callback()`：`BC_NOTIFY_IND` → `handle_notification()`；否则 `handle_message()`
   - `handle_notification()`：按 `notification` 更新 **battery / usb / usb_2 / wireless** psy，触发 `power_supply_changed`、`usb_type_work` 等
   - `read_property_id()` / `battery_chg_update_usb_type_work`：经 glink **GET** 同步属性（具体见源码）
2. **`transsion/glink/`**（按产品配置）
   - 与 `qti_battery_charger` 通过 **头文件**（如 `tc_sys_attr.h` / `tc_sys.h`）及 **同名 power_supply**（如 `tc_water`）耦合；以本机 `obj-$(CONFIG_*)` 为准。

## 主链路（概念）

```text
ADSP / PMIC 固件
  -> pmic_glink (MSG_OWNER_BC)
  -> battery_chg_callback
  -> handle_notification | handle_message
  -> read_property_id (GET) / 缓存 prop
  -> power_supply_changed (usb/battery/wireless)
  -> userspace / healthd / framework
```

## 分析步骤

```text
qcom power_supply 排查清单
- [ ] 确认 qti_battery_charger probe 成功、glink UP（battery_chg_state_cb）
- [ ] BC_NOTIFY_IND 是否到达、handle_notification 分支是否匹配
- [ ] usb psy：USB_TYPE / USB_ADAP_TYPE / ONLINE 与现象是否一致
- [ ] 是否混入 Transsion：搜 tc_ / CONFIG_TC_SYS / tc_water
- [ ] 与 UCSI 混淆时：connector 走 ucsi skill，充电类型走本 skill
```

## 日志锚点

- `BATTERY_CHG:`（`pr_fmt`）
- `notification:` / `owner:` / `opcode:`（调试级别）

## 转交

- **glink BC/UC 交界**：`qualcomm-kernel-adsp-bridge`
- **UCSI / typec connector**：`qualcomm-msm-kernel-usb-ucsi-analysis`
- **role switch / dwc3 / gadget 枚举**：`qualcomm-msm-kernel-dwc3-role-gadget-analysis`
- **ADSP 充电识别 / ICM**：`qualcomm-adsp-charging-analysis`
- **ADSP PD 协议栈**：`qualcomm-adsp-usb-pd-analysis`

## 附加资料

- Makefile/Kconfig、psy 名称与 Transsion 模块列表见 [reference.md](reference.md)
