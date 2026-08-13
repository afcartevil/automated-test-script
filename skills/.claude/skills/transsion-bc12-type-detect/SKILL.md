---
name: transsion-bc12-type-detect
description: "Transsion-BC1.2: 分析BC1.2和charger type detect路径，覆盖tc_chg_type_det、usb ready、cdp-block | bc12/usb_ready/cdp_block/port_stat/charger_type/SDP/CDP/DCP | 当用户报告充电类型识别失败、DCP/SDP识别错误、usb_ready长期为0时使用"
funcType: "AI故障分析"
category: "驱动"
---

# Transsion BC1.2 Type Detect

## 适用范围

聚焦 `tc_chg_type_det.c` 的 attach 处理、worker 调度、BC1.2 前置等待、具体 charger ops 调用、结果回写。

包含：
- `drivers/power/supply/transsion/tc_chg_type_det.c`
- `drivers/power/supply/transsion/tc_charger_class.c`
- 具体 charger IC 的 type detect ops
- `is_usb_rdy()` 与 `cdp-block` 门控
- `tfcp_adapter det_done` 对 PD attach 放行时机的影响
- `非标 / SDP / DCP` 三类 attach 结果的分支处理

不包含：
- `tc_charger.c` 的 vote 聚合与主控策略
- PD policy engine 细节
- `tran_extcon_usb.c` 的角色桥接内部逻辑
- MTU3 枚举细节

## 固定入口

优先从以下函数开始：
1. `tc_detect_probe()`
2. `tc_pd_tcp_notifier_call()`
3. `handle_typec_pd_attach()`
4. `typec_attach_thread()`
5. `tc_detect_bc12_work()`
6. `do_bc12_pre_work()`
7. `is_usb_rdy()`
8. `tc_detect_bc12_run()`

charger class 入口：
- `charger_device_register()`
- `get_charger_by_name()`
- `charger_dev_enable_chg_type_det()`
- `charger_dev_get_port_stat()`
- `charger_dev_get_vbus_gd()`

## 关键主链

```text
TCPC attach event
-> tc_pd_tcp_notifier_call()
-> handle_typec_pd_attach()
-> typec_attach_thread()
-> tc_detect_bc12_work()
-> do_bc12_pre_work()
-> tc_detect_bc12_run()
-> charger_dev_* ops on primary_chg
-> power_supply_changed()
-> TRAN_PROP_WAKE_UP_CHARGER
```

## 充电图标关联（healthd online 视角）

图标是否出现，最终取决于上层是否在 `power_supply` 中读到可用电源 `online=1`。

- AOSP `healthd`（`system/core/healthd/BatteryMonitor.cpp`）会：
  - 扫描 `mChargerNames`（具备 `type` 且有 `online` 节点的电源）
  - 读取 `/sys/class/power_supply/<name>/online`
  - 若在线，再按 `type` 归类到 AC/USB/WIRELESS
- 本模块对应关系：
  - `tc_detect_do_bc12()` 根据 attach/BC1.2 结果写入 `wired_psy` 的 `ONLINE/TYPE/USB_TYPE`
  - 然后 `power_supply_changed(tcd->chg_psy)` 通知上层
  - `tc_detect_get_charger_online()` 由 `wired_online || wireless_online` 决定

因此“图标不出现”在本层的可观测根因通常是：
- attach 很快回到 `TC_ATTACH_TYPE_NONE`
- 结果被写回 `psy_type:Unknown, usb_type:Unknown`
- `online` 被拉回 `0`

## 三类场景分支

- `TC_ATTACH_TYPE_TYPEC`
  - 先走 `do_bc12_pre_work()`
  - 再走 `tc_detect_bc12_run()`
  - 最终依据 `port_stat` 产出 `psy_type` / `usb_type`
- `TC_ATTACH_TYPE_PD_SDP`
  - 不再跑 BC1.2 端口检测
  - 直接设置：
    - `psy_type = POWER_SUPPLY_TYPE_USB`
    - `usb_type = POWER_SUPPLY_USB_TYPE_SDP`
- `TC_ATTACH_TYPE_PD_DCP`
  - 不再跑 BC1.2 端口检测
  - 直接设置：
    - `psy_type = POWER_SUPPLY_TYPE_USB_DCP`
    - `usb_type = POWER_SUPPLY_USB_TYPE_DCP`
- `TC_ATTACH_TYPE_PD_NONSTD`
  - 不再跑 BC1.2 端口检测
  - 直接设置：
    - `psy_type = POWER_SUPPLY_TYPE_USB`
    - `usb_type = POWER_SUPPLY_USB_TYPE_DCP`

分析时必须区分两层：
- 检测结果层：`port_stat` 真正返回了什么
- 对外呈现层：最终被写回 `wired_psy/chg_psy` 的 `psy_type` / `usb_type` 是什么

尤其要注意：
- `PD_NONSTD` 在对外呈现上会落成 `USB + DCP`
- `UNKNOWN_TA` 在 `tc_detect_bc12_run()` 中也会被映射到 `DCP`
- 因此“外显是 DCP”不等于“标准 DCP 充电器”

## 非标 / Unknown TA retry 机制

- `tc_detect_bc12_run()` 中，若 `port_stat` 为：
  - `TC_PORT_STAT_NOINFO`
  - `TC_PORT_STAT_UNKNOWN_TA`
  会先对外暂时落成：
  - `psy_type = POWER_SUPPLY_TYPE_USB`
  - `usb_type = POWER_SUPPLY_USB_TYPE_DCP`
- 但此时不会立即认定 BC1.2 完成，而是：
  - `tcd_set_bc12_complete(tcd, false)`
  - `tc_detect_start_bc12_retry_timer(tcd)`
- retry 定时器使用：
  - `bc12_retry_timer`
  - 间隔来自 dts `bc12_retry_interval`
  - 未配置时默认 `1s`
- timer 触发后进入 `tc_detect_bc12_retry_work()`：
  - 再次执行 `do_bc12_pre_work()`
  - 重新 `charger_dev_enable_chg_type_det()`
  - 最多轮询约 10 次 `port_stat`
- retry 结果分两类：
  - 若拿到 `DCP / SDP / CDP`，就正式写回结果，`tcd_set_bc12_complete(tcd, true)`，并唤醒 `tc_charger`
  - 若仍是 `NOINFO / UNKNOWN_TA`，继续下一轮 retry
- retry 轮次上限：
  - `bc12_retry_cnt++ < 10`
  - 超过后停止 retry，置 `bc12_complete = true`，唤醒 `tc_charger`
- attach 变化或拔出时会停止 retry：
  - `attach changed, stop bc12 retry, reset param`
  - `Adapter plug out, stop retry`

## cdp-block 门控重点

- `is_usb_rdy()` 通过 USB 节点的 `cdp-block` 判断 ready：
  - `ready = !of_property_read_bool(node, "cdp-block")`
- `do_bc12_pre_work()` 在 attach 状态下会循环等待 USB ready：
  - 每 100ms 检查一次
  - 最长约 25 秒
  - attach 变为 `NONE` 时会提前退出
- 运行时清除点不在本模块，而在 `drivers/usb/mtu3/mtu3_gadget.c`
  - `mtu3_gadget_pullup()` 首次 `is_on`
  - `mtu3_gadget_set_ready()`
  - `of_remove_property(..., "cdp-block")`

结论上要区分：
- BC1.2 本身失败
- BC1.2 被 `cdp-block` 长期阻塞
- attach 状态变化导致 BC1.2 中途被打断
- 具体 charger IC 的 port stat / vbus gd 返回异常

## PD_WAIT_BC12 交点

- `tcpc` 侧的 `pd_put_cc_attached_event()` 可能不会立即把 `PD_HW_CC_ATTACHED` 入队。
- 若 `POWER_SUPPLY_PROP_USB_TYPE` 仍为 `UNKNOWN`，PD 会被 `TYPEC_RT_TIMER_PD_WAIT_BC12` 暂时拦住。
- 在 `CONFIG_TC_CHARGER` 场景下，还会额外等待 `tcpci_get_pe50_det_done()` 为 true。
- `tcpci_get_pe50_det_done()` 实际读取的是 `tfcp_adapter` 的 `get_det_done()`，也就是 RFC detect 完成态。
- 因此本 skill 需要回答的不只是“BC1.2 有没有结果”，还包括：
  - 这个结果是否已经足以放行 PD attach
  - RFC detect 是否仍未完成，导致 PD 继续被等待门拦截

## 分析步骤

```text
BC1.2/type detect 排查清单
- [ ] 先确认 attach 事件是否进入 tc_chg_type_det
- [ ] 跟踪 worker 是否被正确唤醒
- [ ] 跟踪 is_usb_rdy() 与 cdp-block 门控
- [ ] 跟踪 tc_detect_bc12_run() 调到哪个 charger_dev_* ops
- [ ] 区分当前场景属于 `TYPEC` 检测路径，还是 `PD_SDP` / `PD_DCP` / `PD_NONSTD` 直设路径
- [ ] 对 `TYPEC` 检测路径，确认 `port_stat` 最终落成 `SDP / DCP / UNKNOWN_TA / CDP`
- [ ] 对 `PD_NONSTD`，确认是否出现“对外看起来像 DCP，但本质是非标”的情形
- [ ] 若 `port_stat` 为 `UNKNOWN_TA / NOINFO`，检查是否已进入 `bc12_retry_timer` 与 `bc12_retry_work`
- [ ] 检查 `bc12_retry_interval`、`bc12_retry_cnt`、停止条件以及最终是否强制 `bc12_complete = true`
- [ ] 确认 port stat / vbus gd / online / usb_type 的最终结果
- [ ] 对“图标不出现”场景，补一条在线状态链：`tc_detect_do_bc12(...)` -> `tc_detect_get_charger_status(... online:x,y ...)` -> `mtk_battery_external_power_changed ... online:0/1`
- [ ] 若 PD 没启动，检查 `PD_WAIT_BC12` 是否仍在等待 `USB_TYPE_UNKNOWN` 或 `tfcp_adapter det_done`
- [ ] 区分“检测层失败”与“主控策略层未消费检测结果”
```

图标场景关键词（优先分流到本 skill）：
- `tc_detect_do_bc12:attach:TC_ATTACH_TYPE_*`
- `psy_type:Unknown` / `usb_type:Unknown`
- `tc_detect_get_charger_status: ... online:0,0`
- `mtk_battery_external_power_changed ... online:0`
- `mtk-extcon-usb ... online=0, type=0`

与上游联动提示：
- 若同时存在 `CC_Alert 1/0`、`1/1`、`2/1` 高频抖动，优先回溯上游 TCPC 稳定性，重点怀疑拓展坞/接口/线材等外部链路问题。

## 输出模板

```markdown
## 触发点
- 输入触发：<attach / bc12 / cdp-block / usb ready>
- 首个命中函数：<function>

## 检测路径
- attach 链：<call chain>
- BC1.2 链：<call chain>
- charger ops：<enable/get_port_stat/get_vbus_gd>
- 场景分支：<TYPEC 检测 / PD_SDP 直设 / PD_DCP 直设 / PD_NONSTD 直设>

## 门控判断
- usb ready：<0/1 + 依据>
- cdp-block：<存在/已清除 + 依据>
- pd wait gate：<是否卡在 `TYPEC_RT_TIMER_PD_WAIT_BC12` + 原因>
- retry 状态：<未触发 / retry 中 / retry 结束 + 当前计数>

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 转交条件

- 若根因在 `tcpci_alert()` 之前的附着或 PD 事件，转交 `mediatek-pd-typec-protocol-6-12`
- 若根因在 `tc_tcpc.c` 的事件映射，转交 `transsion-tcpc-adapter`
- 若 `cdp-block` 长时间不释放，次域通常是 `mtu3-usb-device-core`
- 若 BC1.2 已稳定为 DCP，且问题进入快充探测/选型：外层 `support_alg` / `tc_algo_protocol_process` / `data->running_algo`，或 PE5 内层 `tfcp_adapter / pd_adapter / hvdcp30_adapter` / `support_ta` / `PE50_*`，转交 `transsion-dcp-fastcharge-probe`
- 若 BC1.2 已完成但 `tc_charger` 后续策略异常，转交 `transsion-charger-orchestrator`

## 约束

- 回答时必须明确区分“检测层”和“主控策略层”
- 不能把 `cdp-block` 问题直接等同于 BC1.2 算法失败
- 对“图标不出现”场景，必须明确回答：`online` 是在哪一步被置 1，又在哪一步被拉回 0
- 若需要引用具体 IC，实现优先从 `mt6375-charger.c`、`tc_sgm41516d.c`、`tc_rt9471.c` 中寻找 `chg_ops`
- 若在 BC1.2 窗口同时看到 RFC/PD/HVDCP/TC30/PE 等“握手失败”日志，不能直接据此下“链路异常”结论；需先核对充电器是否声明支持该协议
- 若对端协议能力未知，必须显式标注“能力未知，当前仅能判定协商未成功”，禁止将其作为 BC1.2 侧异常证据
