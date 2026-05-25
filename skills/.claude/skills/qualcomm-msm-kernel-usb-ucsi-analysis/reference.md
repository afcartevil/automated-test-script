# Qualcomm msm-kernel UCSI Reference

## Kconfig（本树摘录）

- `TYPEC_UCSI`：核心 `typec_ucsi`（`ucsi.o`）
- `UCSI_QTI_GLINK`：depends on `QTI_PMIC_GLINK`，模块名 **`ucsi_glink`**
- 其它后端：`UCSI_ACPI`、`UCSI_CCG`、`UCSI_STM32G0`（高通手机常见为 **Glink**）

## ucsi_glink：opcode 与数据流

| opcode | 处理函数 | 说明 |
|--------|----------|------|
| `UC_UCSI_READ_BUF_REQ` | `handle_ucsi_read_ack()` | 固件应答读缓冲，唤醒 `read_ack` |
| `UC_UCSI_WRITE_BUF_REQ` | `handle_ucsi_write_ack()` | 写应答 |
| `UC_UCSI_USBC_NOTIFY_IND` | `handle_ucsi_notify()` | **异步通知**；解析 `notification` 为 CCI，调 `ucsi_connector_change()` |

`ucsi_qti_ops` 将 `read` / `sync_write` / `async_write` 接到通用 UCSI 核心。

## 与 `qti_battery_charger` 的差异

- **不同 glink client**：UC 用 `MSG_OWNER_UC`（32779），BC 用 `MSG_OWNER_BC`（32778）。
- **现象分流**：端口/CCI/connector/typec 类 → 先 **ucsi**；`usb`/`battery` sysfs 上充电类型、电流、SOC → 先 **qti_battery_charger**。

## 平台设备

- `compatible = "qcom,ucsi-glink"`
- driver name：`ucsi_glink`

## 现象映射

| 现象 | 优先检查 |
|------|----------|
| 插拔后 UCSI 无通知 | `PMIC_GLINK_STATE_DOWN`、notify 是否到达、`handle_ucsi_notify` |
| UCSI 命令超时 | `ucsi_qti_read` / `ucsi_qti_glink_write` 的 `wait_for_completion_timeout` |
| CCI 有变化但 connector 不更新 | `ucsi_connector_change` 路径、`con_num` 与 `num_connectors` |
| role 已变但 device/host 枚举链不对 | 转 `qualcomm-msm-kernel-dwc3-role-gadget-analysis` |

## 最小结论模板

```markdown
## 组件
- ucsi_glink / ucsi core / psy

## 证据
- glink state: UP/DOWN
- 最后一条 notify/read 日志: <snippet>

## 断点
- 函数: <...>

## 下一步
- <reference 或转交 skill>
```
