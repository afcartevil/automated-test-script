# Qualcomm Kernel ↔ ADSP Reference

## 仓库内路径（本树）

- 桥接中枢：[`vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/qti_battery_charger.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/qti_battery_charger.c)
- UCSI Glink：[`vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/ucsi_glink.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/ucsi_glink.c)
- Kconfig：`UCSI_QTI_GLINK` depends on `QTI_PMIC_GLINK`（[`drivers/usb/typec/ucsi/Kconfig`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/Kconfig)）

## 1. `qti_battery_charger`：glink 消息与回调

| 入口 | 作用 |
|------|------|
| `battery_chg_callback()` | 所有 BC 客户端消息；`opcode == BC_NOTIFY_IND` 走通知，否则走 `handle_message()` |
| `handle_notification()` | 解析 `notification` 字段，对 `battery` / `usb` / `usb_2` / `wireless` 的 `psy_state` 调度 `power_supply_changed()` |

`handle_notification()` 中典型 `notification` 值（与固件约定，见源码枚举）：

| notification（概念） | 行为摘要 |
|----------------------|----------|
| `BC_BATTERY_STATUS_GET` / `BC_GENERIC_NOTIFY` | 更新 battery psy；可选触发 `battery_check_work` |
| `BC_USB_STATUS_GET(port0)` | 置 `usb_active[0]`，调度 `usb_type_work`（及本机型的 `tc_work` 等） |
| `BC_USB_STATUS_GET(port1)` | 双口时同理，USB_2 psy |
| `BC_WLS_STATUS_GET` | wireless psy |
| 其它（如 `BC_HBOOST_VMAX_CLAMP_NOTIFY`） | 专用分支，可能走 `hboost_notifier` |

`battery_chg_probe()` 注册：

- `client_data.id = MSG_OWNER_BC`
- `msg_cb = battery_chg_callback`
- `compatible = "qcom,battery-charger"`

## 2. `ucsi_glink`：glink 消息与回调

| opcode | handler | 作用 |
|--------|---------|------|
| `UC_UCSI_READ_BUF_REQ` | `handle_ucsi_read_ack()` | 填充 UCSI 缓冲区读应答 |
| `UC_UCSI_WRITE_BUF_REQ` | `handle_ucsi_write_ack()` | 写应答 |
| `UC_UCSI_USBC_NOTIFY_IND` | `handle_ucsi_notify()` | 解析 CCI 通知，调用 `ucsi_connector_change()` |

`ucsi_probe()` 注册：

- `client_data.id = MSG_OWNER_UC`
- `msg_cb = ucsi_callback`
- `compatible = "qcom,ucsi-glink"`

核心操作结构：`ucsi_qti_ops`（`read` / `sync_write` / `async_write`）由 `ucsi_create()` 挂到通用 [`ucsi.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/ucsi.c) 状态机。

## 3. 与 ADSP skill 的对应（概念）

| ADSP（固件） | Kernel 落点 |
|--------------|-------------|
| `PPM` / UCSI mailbox / CCI | `ucsi_glink` + `ucsi` core |
| `DPM` / charger 通知 / USB 电源属性 | `qti_battery_charger` + `power_supply` |
| `pmic_glink_send_notification`（固件） | 上述两客户端之一收到异步消息 |

## 4. grep / dmesg 锚点

- `BATTERY_CHG:`（`qti_battery_charger.c` 的 `pr_fmt`）
- `UCSI:`（`ucsi_glink.c` 的 `pr_fmt`）
- `owner:` / `opcode:`（`battery_chg_callback` 调试打印）

## 5. 易混点

- **USB 充电类型** 多在 **BC** 的 `usb`/`usb_2` power_supply（`USB_*` 属性 id），与 **UCSI connector 状态** 是不同子系统；需同时看时分别从两条 skill 下钻。
- **glink DOWN** 时：`ucsi_qti_read/write` 可能直接返回 0 或超时；`qti_battery_charger` 中亦有对 `read_property_id` 失败时的降级（视机型补丁而定）。
- 若 BC/UC 都合理，但仍出现 role 或 gadget 枚举异常，转 `qualcomm-msm-kernel-dwc3-role-gadget-analysis`。
