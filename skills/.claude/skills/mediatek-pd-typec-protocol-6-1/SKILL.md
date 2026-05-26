---
name: mediatek-pd-typec-protocol-6-1
description: "MTK-PD协议-6.1: 基于6.1内核分析PD IC与Type-C协议路径，覆盖CC_ALERT/ps_change到tcpc事件队列和policy engine | PD协商/role_swap/插拔异常/tcpc协议栈 | 当用户报告MTK 6.1内核设备PD协商失败、Type-C插拔异常时使用。6.12内核走mediatek-pd-typec-protocol-6-12"
funcType: "AI故障分析"
category: "驱动"
---

# MediaTek PD Type-C 协议栈（6.12）

## 适用范围

聚焦 6.12 树中的 PD IC 驱动与 Type-C/PD 协议框架。

主路径：
- `kernel/kernel_device_modules-6.12/drivers/misc/mediatek/typec/tcpc`

包含：
- Alert 位解析、CC 变化处理、Power Status 处理
- Type-C 状态迁移与附着/解附着
- PD 事件入队/出队与 Policy Engine 循环

不包含：
- `tc_charger` 的充电策略投票
- MTU3 USB 核心枚举细节
- battery/gauge 的 SOC 算法细节

## 固定入口

必须从这里开始：
1. `tcpci_alert.c` 中 `tcpci_alert()`
2. CC 链路：`tcpci_alert_cc_changed()` -> `tcpc_typec_handle_cc_change()`
3. 电源链路：`tcpci_vbus_level_changed()` -> `tcpc_typec_handle_ps_change()`

PD 事件与 PE 链路：
- `pd_put_*_event()` / `pd_get_event()` in `tcpci_event.c`
- `tcpc_event_thread_fn()` in `tcpci_event.c`
- `pd_policy_engine_run()` in `pd_policy_engine.c`

关键日志锚点：
- `TYPEC_INFO("[CC_Alert] ...")`
- `TCPC_INFO("ps_change=%d", ...)`

## 分析步骤

```text
PD/Type-C 排查清单（6.12）
- [ ] 在 tcpci_alert_handlers[] 中确认 alert 位与处理函数
- [ ] 跟踪 CC_ALERT -> tcpc_typec_handle_cc_change() -> 附着状态变化
- [ ] 跟踪 ps_change -> tcpc_typec_handle_ps_change() -> VBUS 分支
- [ ] 跟踪 pd_put_*_event 入队与 tcpc_event_thread_fn() 唤醒
- [ ] 跟踪 pd_policy_engine_run() 对事件的最终处理
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

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 约束

- 根因分析时不能跳过 `tcpci_alert()`，必须从 alert 解码起步
- 必须分离“Type-C 附着逻辑”与“PD 协商逻辑”
- 若问题仅为充电策略行为，转交 charger orchestrator skill
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
- 若仅看到协议握手失败日志（PD/PPS/QC/HVDCP/TC30/PE 等），不能直接推导为协议栈异常；必须先核对对端是否声明支持该协议
- 对端能力未知时，必须在结论中标注“能力未知，当前仅能判定协商未成功”
