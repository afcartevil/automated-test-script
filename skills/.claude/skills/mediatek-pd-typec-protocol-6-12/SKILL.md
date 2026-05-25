---
name: mediatek-pd-typec-protocol-6-12
description: "MTK-PD协议-6.12: 基于6.12内核分析PD IC与Type-C协议路径，覆盖CC_ALERT/ps_change到tcpc事件队列和policy engine | PD协商/role_swap/插拔异常/tcpc协议栈 | 当用户报告MTK 6.12内核设备PD协商失败、Type-C插拔异常时使用。6.1内核走mediatek-pd-typec-protocol-6-1，TypeC整体分析走mediatek-pd-typec-analysis"
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
- `CC_ATTACHED` 入队前的 `PD_WAIT_BC12` 等待门

不包含：
- `tc_tcpc.c` 的 Transsion 事件适配细节
- `tc_charger` 的充电策略投票
- MTU3 USB 核心枚举细节
- battery/gauge 的 SOC 算法细节

## 固定入口

必须从这里开始：
1. `tcpci_alert.c` 中 `tcpci_alert()`
2. CC 链路：`tcpci_alert_cc_changed()` -> `tcpc_typec_handle_cc_change()`
3. 电源链路：`tcpci_vbus_level_changed()` -> `tcpc_typec_handle_ps_change()`

PD 事件与 PE 链路：
- `tcpci_event.c` 中 `pd_put_*_event()` / `pd_get_event()`
- `tcpci_event.c` 中 `tcpc_event_thread_fn()`
- `pd_policy_engine.c` 中 `pd_policy_engine_run()`

`CC_ATTACHED` 等待门：
- `tcpci_event.c` 中 `pd_put_cc_attached_event()` / `__pd_put_cc_attached_event()`
- `tcpci_typec.c` 中 `typec_handle_pd_wait_bc12()`
- `tcpci_timer.c` 中 `TYPEC_RT_TIMER_PD_WAIT_BC12`
- `tcpci.c` 中 `tcpci_get_pe50_det_done()`

关键日志锚点：
- `TYPEC_INFO("[CC_Alert] ...")`
- `TCPC_INFO("ps_change=%d", ...)`

## 分析步骤

```text
PD/Type-C 排查清单（6.12）
- [ ] 在 tcpci_alert_handlers[] 中确认 alert 位与处理函数
- [ ] 跟踪 CC_ALERT -> tcpc_typec_handle_cc_change() -> 附着状态变化
- [ ] 跟踪 ps_change -> tcpc_typec_handle_ps_change() -> VBUS 分支
- [ ] 检查 `pd_put_cc_attached_event()` 是否被 `TYPEC_RT_TIMER_PD_WAIT_BC12` 拦截
- [ ] 检查等待条件：`POWER_SUPPLY_PROP_USB_TYPE` 是否仍为 `UNKNOWN`
- [ ] 检查等待条件：`tcpci_get_pe50_det_done()` / `tfcp_adapter det_done` 是否完成
- [ ] 检查 `typec_handle_pd_wait_bc12()` 是否每 50ms 重试并最终调用 `__pd_put_cc_attached_event()`
- [ ] 跟踪 pd_put_*_event 入队与 tcpc_event_thread_fn() 唤醒
- [ ] 跟踪 pd_policy_engine_run() 对事件的最终处理
```

## 充电图标不出现：TCPC 抖动/风暴首诊（本层）

当现象是“插入充电器后概率性不出图标”，先在本层排除 Type-C 侧抖动：

- 关键征象（任意命中即高风险）：
  - `TCPC-TYPEC:[CC_Alert] 7/5`、`7/6`、`7/0` 高频反复
  - `TCPC-TYPEC:Attached-> NULL` 与 attach 状态来回跳变
  - `TCPC-TCPC:Alert:0x...` 高频出现，且紧邻 `CC_Alert` 抖动
- 结论语义：
  - 本层不直接判“图标逻辑错误”，而是先判定“Type-C 输入是否稳定”
  - 若输入不稳定，后续 `TC_TCPC` 与 `BC1.2` 会被反复触发/撤销，导致上层 `online` 抖动

推荐输出句式：
- `Type-C 原生输入抖动，先触发 USB attach，又快速回到 unattached；后续层级收到的是抖动事件流，而非稳定插入。`

### CC 形态指纹（外部链路优先怀疑）

若在抖动窗口内反复看到以下组合，优先怀疑外部链路不稳定：

- `CC_Alert 1/0`、`1/1`、`2/1`（含与 `0/x`、`7/x` 交替）
- 同时出现 `USB Plug in/out` 频繁切换、`Attached-> NULL` 翻转

优先怀疑对象（从高到低）：
- 外接拓展坞（dock/hub）异常，导致 CC 状态不稳
- 手机 C 口脏污或接触不良
- 数据线品质不佳
- 充电器或对端端口状态不稳

规则化结论：
- 若 `1/0`、`1/1`、`2/1` 在同一插入窗口频繁出现，输出中应明确“**着重怀疑拓展坞侧**”。
- 该结论属于高概率工程线索，不是单点确诊；必须绑定“CC 组合 + 翻转频次”证据。

## PD_WAIT_BC12 等待门

- `pd_put_cc_attached_event()` 不是总会立即把 `PD_HW_CC_ATTACHED` 入队。
- 对 sink attach：
  - 若 `POWER_SUPPLY_PROP_USB_TYPE` 仍为 `UNKNOWN`
  - 或 `tcpci_get_pe50_det_done()` 返回 false
  - 会先启动 `TYPEC_RT_TIMER_PD_WAIT_BC12`
- `TYPEC_RT_TIMER_PD_WAIT_BC12` 在 `tcpci_timer.c` 中每 50ms 触发一次。
- 超时处理在 `typec_handle_pd_wait_bc12()`：
  - 若条件满足，则调用 `__pd_put_cc_attached_event()`
  - 否则继续 re-arm timer
- 结论上必须区分：
  - “PD 事件没有生成”
  - “PD 事件已经生成，但 `CC_ATTACHED` 还被等待门拦在入队前”

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
- 等待门：<是否命中 PD_WAIT_BC12 + 条件 + 重试次数>
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
- 分析 `PD_HW_CC_ATTACHED` 前必须先判断是否被 `PD_WAIT_BC12` 门控
- 对“充电图标不出现”场景，必须先判断是否存在 `CC_Alert` 高频抖动；未确认前不要直接归因到 BC1.2
- 若原生 `TCP_NOTIFY_*` 正常，但 `tc_tcpc.c` 向上层转换异常，转交 `transsion-tcpc-adapter`
- 若等待门卡在 `USB_TYPE_UNKNOWN` 或 RFC det_done 未完成，次域通常转交 `transsion-bc12-type-detect`
- 若问题仅为充电策略行为，转交 `transsion-charger-orchestrator`
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
- 若仅看到协议握手失败日志（PD/PPS/QC/HVDCP/TC30/PE 等），不能直接推导为协议栈异常；必须先核对对端是否声明支持该协议
- 对端能力未知时，必须在结论中标注“能力未知，当前仅能判定协商未成功”
