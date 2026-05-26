---
name: transsion-tcpc-adapter
description: "Transsion-TCPC适配: 分析tc_tcpc适配层，定位MTK TCP_NOTIFY→TC_TYPEC/TC_PD事件映射 | tc_tcpc/TCP_NOTIFY/TC_TYPEC/TC_PD/DR_SWAP/TypeC事件 | 当用户报告上层收不到正确Type-C/PD事件、DR_SWAP异常时使用。TypeC协议走mediatek-pd-typec-analysis"
funcType: "AI故障分析"
category: "驱动"
---

# Transsion TCPC 适配层

## 适用范围

聚焦 `tc_tcpc.c` 如何把 MediaTek TCPC notifier 事件转换为 Transsion 内部事件。

包含：
- `drivers/power/supply/transsion/tc_tcpc.c`
- `drivers/power/supply/transsion/tc_tcpc.h`
- `register_tcp_dev_notifier()` 到 `register_tc_tcpc_notifier()` 的适配边界
- `TCP_NOTIFY_*` 到 `TC_TYPEC_*` / `TC_PD_*` 的事件翻译

不包含：
- 原生 PD policy engine 细节
- `tran_extcon_usb.c` 的角色桥接
- `tc_chg_type_det.c` 的 BC1.2 检测
- `tc_charger.c` 的策略 vote 与插拔编排

## 固定入口

优先从以下入口开始：
1. `register_tc_tcpc_notifier()`
2. `tc_pd_tcp_notifier_call()`
3. `tc_tcpc_notify()`

补查原生 notifier 注册入口：
- `drivers/misc/mediatek/typec/tcpc/tcpci_core.c` 的 `register_tcp_dev_notifier()`

## 关键映射关系

- `TCP_NOTIFY_TYPEC_STATE`
  - 映射到 `TC_TYPEC_USB_PLUG_IN`
  - 映射到 `TC_TYPEC_USB_PLUG_OUT`
  - 映射到 `TC_TYPEC_OTG_PLUG_IN`
  - 映射到 `TC_TYPEC_OTG_PLUG_OUT`
  - 以及角色方向事件如 `TC_PD_SRC_TO_SNK` / `TC_PD_SNK_TO_SRC`
- `TCP_NOTIFY_DR_SWAP`
  - 映射到 `TC_PD_DR_SWAP_NEW_ROLE`
- `TCP_NOTIFY_PD_STATE`
  - 映射到 `TC_PD_TYPE`

## 分析步骤

```text
TCPC 适配层排查清单
- [ ] 先确认原始事件来自哪个 TCP_NOTIFY_* 类型
- [ ] 跟踪 tc_pd_tcp_notifier_call() 的分支与 payload 填充
- [ ] 确认 tc_tcpc_notify() 是否把事件广播给所有注册者
- [ ] 对照 tc_tcpc.h 中枚举，确认 Transsion 事件是否选对
- [ ] 区分“原生 TCPC 没上报”与“适配层映射错误”
```

## 充电图标不出现：适配层抖动识别

当目标问题是“插入后概率性不出充电图标”，本层优先确认是否出现“事件翻转风暴”：

- 关键日志锚点：
  - `[TC_TCPC] ... USB Plug in`
  - `[TC_TCPC] ... USB Plug out`
  - `[TC_CHG_THREAD]tc_chg_tcpc_notifier_call 12`（常对应插入链）
  - `[TC_CHG_THREAD]tc_chg_tcpc_notifier_call 7`（常对应拔出链）
- 风险判据：
  - `Plug in` 和 `Plug out` 在短窗口内反复交替，说明下游 `tc_chg_type_det` 会反复收到 `TYPEC` / `NONE`
  - 此时优先结论是“输入事件不稳定”，而不是直接结论“BC1.2 算法错误”

推荐输出句式：
- `适配层映射本身可达，但输入事件出现连续 12/7 翻转，导致下游 attach 状态来回切换。`

补充判据（与原生层联动）：
- 若同窗还命中 `CC_Alert 1/0`、`1/1`、`2/1`，在适配层结论中追加：
  - `输入抖动更像外部链路（尤其拓展坞）引发，而非适配映射逻辑本身。`

## 输出模板

```markdown
## 触发点
- 输入触发：<TCP_NOTIFY_* / 日志 / 症状>
- 首个命中函数：<function>

## 适配路径
- 原生事件：<TCP_NOTIFY_*>
- 转换事件：<TC_TYPEC_* / TC_PD_*>
- 广播链：register_tcp_dev_notifier -> tc_pd_tcp_notifier_call -> tc_tcpc_notify

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 转交条件

- 若 `tcpci_alert()` 之前的 CC / VBUS / PD 事件本身异常，转交 `mediatek-pd-typec-protocol-6-12`
- 若 `TC_TYPEC_*` 已正确产生，但角色桥接错误，转交 `transsion-extcon-usb-role-bridge`
- 若 `TC_TYPEC_*` 已正确产生，但 BC1.2 检测路径异常，转交 `transsion-bc12-type-detect`

## 约束

- 只定位“事件适配是否正确”，不直接下结论到充电策略或 USB 枚举
- 回答时必须同时给出“原生事件名”和“转换后的 Transsion 事件名”
- 对“图标不出现”场景，必须给出 `12/7`（或 `USB Plug in/out`）是否翻转的结论
- 若无法证明映射错误，不要跳过原生 TCPC 层直接下结论
- 若下游日志出现 RFC/PD/HVDCP/TC30/PE 等握手失败，不能在本层直接判定“协议链路异常”；需先核对充电器是否支持对应协议
- 对端能力未知时，必须标注“能力未知，当前仅能判定协商未成功”
