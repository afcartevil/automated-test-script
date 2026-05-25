---
name: mediatek-pd-typec-analysis
description: "MTK-TypeC/PD: 分析Type-C/PD插拔行为与协议栈路径 | CC_ALERT/ps_change/PD协商/tcpc/TypeC附着/解附着 | 当用户报告MTK设备Type-C插拔异常、PD协商失败时使用。协议细节走mediatek-pd-typec-protocol-6-1或6-12，TCPC适配走transsion-tcpc-adapter"
---

# MediaTek PD Type-C 分析（6.12）

## 说明

这个 skill 用于：
- 跟踪 Type-C 状态机中的插拔迁移
- 跟踪 `CC_ALERT` / `ps_change` 如何从 TCPC 驱动进入 PD 协议栈
- 定位 PD 事件如何入队、消费、进入 policy engine

主路径（6.12）：
- `kernel/kernel_device_modules-6.12/drivers/misc/mediatek/typec/tcpc`

如果用户给了其他树根，只保留相对路径 `drivers/misc/mediatek/typec/tcpc` 做映射。

## 固定入口

先从这四组入口开始：

1) IRQ/Alert 分发：
- `tcpci_alert.c` 中 `tcpci_alert()`
- `tcpci_alert.c` 中 `tcpci_alert_handlers[]`

2) CC 附着起点：
- `tcpci_alert_cc_changed()` -> `tcpc_typec_handle_cc_change()`

3) 电源变化起点（`ps_change`）：
- `tcpci_alert_power_status_changed()` -> `tcpci_vbus_level_changed()`
- `tcpci_vbus_level_changed()` 打印 `ps_change=...`
- `tcpc_typec_handle_ps_change()` in `tcpci_typec.c`

4) PD 事件与线程：
- `tcpci_event.c` 中 `pd_put_*_event()` / `pd_get_event()`
- `tcpci_event.c` 中 `tcpc_event_thread_fn()`
- `pd_policy_engine.c` 中 `pd_policy_engine_run()`

## 插拔分析步骤

```text
插拔排查清单
- [ ] 在 tcpci_alert_handlers[] 中确认告警位与处理函数
- [ ] 跟踪 CC 链路：tcpc_typec_handle_cc_change()
- [ ] 跟踪状态迁移：attach/detach 相关入口
- [ ] 确认端口上报：tcpci_report_usb_port_changed()
- [ ] 确认 PD attach/detach 事件是否入队
```

重点观察：
- `TYPEC_INFO("[CC_Alert] ...")`
- `TCPC_INFO("ps_change=%d", ...)`
- attach: `tcpci_report_usb_port_attached()` -> `pd_put_cc_attached_event()`
- detach: `tcpci_report_usb_port_detached()` -> `pd_put_cc_detached_event()`

## ps_change / VBUS 分析步骤

```text
ps_change 排查清单
- [ ] 确认 power alert 位（或合成告警）是否命中
- [ ] 确认 tcpci_vbus_level_changed() 中 ps_change 日志
- [ ] 跟踪 tcpc_typec_handle_ps_change(vbus_level)
- [ ] 检查 VBUS present/absent 分支
- [ ] 确认 pd_put_vbus_changed_event()/pd_put_vbus_safe0v_event()
```

## 输出模板

```markdown
## 触发点
- 输入触发：CC_ALERT / ps_change / RX_STATUS / other
- 首个命中函数：<function>

## Type-C 路径
- 状态流：<old_state> -> <new_state>
- 附着结果：attached/detached + type

## PD 路径
- 入队事件：<event list>
- 事件消费：tcpc_event_thread_fn -> pd_policy_engine_run
- 最终 PE/DPM 动作：<action>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 约束

- 每次都从 `tcpci_alert()` 告警解码起步，不能跳过
- 严格区分“Type-C 附着逻辑”与“PD 协商逻辑”
- 回归对比至少覆盖：
  - `tcpci_alert_handlers[]`
  - `tcpc_typec_handle_cc_change()`
  - `tcpc_typec_handle_ps_change()`
  - `pd_put_*_event()` / `pd_policy_engine_run()`
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
- 若日志仅显示某协议握手失败（PD/PPS/QC/HVDCP/TC30 等），不能直接判定协议栈异常；必须先核对对端是否支持该协议
- 对端能力未知时，结论需显式标注“能力未知，当前仅能判定协商未成功”
