# Qualcomm msm-kernel Charging / power_supply Reference

## 构建与依赖（本树）

[`drivers/power/supply/Makefile`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/Makefile)：

- `subdir-ccflags-y += -I$(srctree)/drivers/power/supply/transsion/glink/`
- `obj-$(CONFIG_QTI_BATTERY_CHARGER) += qti_battery_charger.o`
- `obj-y += transsion/`（整子目录编入）

因此 **`qti_battery_charger.c` 可直接包含 Transsion 提供的头文件**（本机为 `tc_sys_attr.h`、`tc_sys.h`）。

## `qti_battery_charger`：核心结构

| 项 | 内容 |
|----|------|
| platform driver | `name = qti_battery_charger`，`compatible = qcom,battery-charger` |
| glink | `client_data.id = MSG_OWNER_BC`（32778），`name = battery_charger` |
| psy 类型 | `PSY_TYPE_BATTERY` / `USB` / `USB_2` / `WLS`，`opcode_get/set` 映射到 `BC_*` |
| 类设备 | `battery_class.name = qcom-battery`（sysfs 扩展属性） |

通知路径见 `handle_notification()`：`BC_USB_STATUS_GET` → `usb_type_work`；battery → `battery_check_work`（低电关机逻辑）等。

## Transsion 子目录（示例）

[`transsion/glink/Makefile`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/transsion/glink/Makefile) 中模块包括：

- `TC_SYS` → `tc_sys.o`、`tc_sys_attr.o`、云控、自修复等
- `TC_INTERFACE_CLASS`、`TC_WATER_DETECTION`、`TRAN_WIRELESS_MANAGER` 等

具体是否编进内核取决于 **defconfig**；分析问题时以 **`/proc/config.gz` 或 `*.config`** 为准。

## 与 UCSI 的协作方式

- **无直接函数耦合**：UCSI 在 **`ucsi_glink`** 客户端；充电类型在 **`qti_battery_charger`**。
- 用户态可能同时读 **typec** 与 **usb** psy；若不一致，按两条 skill **分别** 取日志对齐固件。

## 现象映射

| 现象 | 优先 |
|------|------|
| 充电类型/USB online 错误 | `qti_battery_charger`，`usb_type_work` / `USB_*` 属性 |
| healthd 读属性失败 | `read_property_id` 返回、glink 异常分支（注意机型补丁） |
| 进水检测 / tc_water | Transsion `tc_*` 与 `tc_up_work` 类逻辑 |
| role/gadget 切换与枚举异常 | 转 `qualcomm-msm-kernel-dwc3-role-gadget-analysis` |

## 最小结论模板

```markdown
## 主线
- qti_battery_charger / transsion 模块: <name>

## 证据
- 最后一笔 BC_NOTIFY_IND / read_property: <snippet>

## 断点
- <function>

## 与 UCSI
- 是否需要并行查 ucsi_glink: yes/no
```
