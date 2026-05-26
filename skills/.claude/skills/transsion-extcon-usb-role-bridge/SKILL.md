---
funcType: "AI故障分析"
category: "驱动"
---
name: transsion-extcon-usb-role-bridge
description: "Transsion-extcon-USB角色桥: 分析tran_extcon_usb桥接逻辑，TCPC+power_supply事件→extcon+usb_role_switch | tran_extcon_usb/extcon/usb_role/角色错乱/DR_SWAP/Host/Device | 当用户报告extcon角色映射错乱、Host/Device/NONE下发异常时使用"
---

# Transsion Extcon USB 角色桥接

## 适用范围

聚焦 `tran_extcon_usb` 的事件桥接与角色映射。

包含：
- `drivers/misc/mediatek/extcon/tran_extcon_usb.c`
- `drivers/power/supply/transsion/tc_tcpc.c` 输出的 `TC_TYPEC_*` / `TC_PD_*` 事件作为输入
- TCPC notifier 事件 -> 角色切换
- power_supply notifier（`charger` phandle / `primary_chg`）-> 角色切换
- extcon 状态与 `usb_role_switch_set_role()`

不包含：
- USB 核心传输细节（`mtu3` 运行时内部）
- PD 协议状态机细节
- 充电策略投票逻辑
- `cdp-block` 清除动作本身

## 固定入口

优先从以下入口开始：
1. `tran_usb_extcon_probe()`
2. `tran_usb_extcon_psy_init()`
3. `tran_usb_extcon_tc_tcpc_init()`

核心回调：
- `tran_extcon_pd_tcpc_notifier()`
- `tran_usb_extcon_psy_notifier()`
- `tran_usb_extcon_set_role()`
- `tran_usb_extcon_update_role()`

## 分析步骤

```text
Extcon 角色桥接排查清单
- [ ] 先识别触发源：TCPC 事件还是 PSY 事件
- [ ] 若来自 TCPC，先确认输入事件是哪个 `TC_TYPEC_*` / `TC_PD_*`
- [ ] 跟踪 notifier 回调及事件值
- [ ] 跟踪角色映射：USB_ROLE_HOST/DEVICE/NONE
- [ ] 验证 extcon_set_state_sync() 顺序
- [ ] 验证 usb_role_switch_set_role() 与最终 c_role
- [ ] 区分“桥接层没下发角色”与“下发成功但 MTU3 没执行”
```

## 边界要点

- 本 skill 负责判断角色是否被正确翻译并下发。
- 本 skill 不负责证明 MTU3 内部是否完成 host/device 切换。
- 若你已经能看到 `usb_role_switch_set_role()` 成功但仍无后续 USB ready，主域通常不再是本 skill。
- `cdp-block` 在本 skill 中只作为跨域提示：
  - 它提示后续 `mtu3_gadget_set_ready()` 可能没有发生
  - 但清除动作不在 `tran_extcon_usb.c`

## 输出模板

```markdown
## 触发点
- 输入触发：<tcpc/psy 事件>
- 首个命中函数：<function>

## 桥接路径
- 回调链：<call chain>
- 角色变化：<old_role> -> <new_role>

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 约束

- 只定位桥接转换层，不深入 USB endpoint 细节
- 若输入事件已经是错误的 `TC_TYPEC_*` / `TC_PD_*`，优先转交 `transsion-tcpc-adapter`
- 若角色已正确下发但枚举失败，转交 `mtu3-usb-device-core`
- 若 TCPC 事件源本身异常，转交 PD-TypeC skill
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
