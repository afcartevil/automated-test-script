---
funcType: "AI故障分析"
category: "驱动"
---
name: mtu3-usb-device-core
description: "MTK-MTU3-USB-Device: 分析MTU3 USB device core与DRD行为，覆盖extcon和usb_role_switch进入MTU3后的角色应用、gadget ready与cdp-block清除 | mtu3/ssusb/USB枚举失败/OTG角色切换/dr_mode异常/gadget_ready/cdp_block | 当用户报告MTK设备USB枚举失败、OTG角色切换异常、gadget ready缺失时使用。Host模式xHCI走mediatek-mtu3-xhci-host，OTG基本路径走mtk-usb20-musb-otg-core"
---

# MTU3 USB 设备核心

## 适用范围

只分析 MTU3 的 USB 核心行为与 DRD 角色应用。

包含：
- `drivers/usb/mtu3/mtu3_dr.c`
- `drivers/usb/mtu3/mtu3_core.c`
- `drivers/usb/mtu3/mtu3_plat.c`
- `drivers/usb/mtu3/mtu3_gadget.c`
- gadget `vbus_draw` 限流与 `usb_psy` 电流门控

不包含：
- PD 协议状态机细节
- 充电策略与投票流程
- 电量计/SOC 逻辑
- MUSB/usb20 控制器路径（如 `using musb-hdrc`、`[MUSB]`、`mt_usb`）
- `tran_extcon_usb.c` 的角色翻译逻辑
- **Host 侧 xHCI 与 `xhci_mtk_probe` 长链**（见 **`mediatek-mtu3-xhci-host`**）

## 固定入口

优先从以下入口开始：
1. `ssusb_set_mode()`
2. `ssusb_role_sw_set()` / `ssusb_role_sw_register()`
3. `ssusb_extcon_register()`
4. `mtu3_gadget_pullup()`

重点补查：
- `mtu3_plat.c` 中 `dr_mode` 初始化
- `mtu3_dr.c` 中 extcon/notifier 回调
- `mtu3_gadget.c` 中 gadget ready 与 `cdp-block` 清除：
  - `mtu3_gadget_pullup()` -> `mtu3_gadget_set_ready()`
  - `of_remove_property(..., "cdp-block")`
- `mtu3_core.c` 中 `mtu3_gadget_vbus_draw()` / `mtu3_vbus_draw_work()`：
  - USB 插入初期的 `vbus draw` 限流
  - 通过 `usb_psy` 下发 current limit

## 分析步骤

```text
MTU3 排查清单
- [ ] 确认 dr_mode 配置（host/peripheral/otg）
- [ ] 确认角色输入源（extcon 或 role_switch）
- [ ] 跟踪 ssusb_set_mode() 的角色切换与结果
- [ ] 检查 host/peripheral 分支初始化
- [ ] 跟踪 mtu3_gadget_pullup() 是否首次成功拉起 gadget
- [ ] 确认 mtu3_gadget_set_ready() 是否执行并清除 cdp-block
- [ ] 检查 `mtu3_gadget_vbus_draw()` 是否被 gadget driver 调用
- [ ] 检查 `mtu3_vbus_draw_work()` 是否通过 `usb_psy` 下发 0mA / 100mA / unlimited
- [ ] 区分“USB 初期功耗受限”与“枚举后恢复正常电流”
- [ ] 区分“输入角色异常”与“核心运行时异常”
```

## cdp-block 边界

- `cdp-block` 不是 MTU3 决策条件，而是 BC1.2 检测侧读取的跨域门控位。
- MTU3 在本 skill 中的职责是：
  - 通过 `mtu3_gadget_pullup()` 进入 gadget ready
  - 通过 `mtu3_gadget_set_ready()` 清除 `cdp-block`
- 因此要区分：
  - 角色已下发，但 MTU3 没切换
  - MTU3 已切到 device，但 gadget pullup 没发生
  - gadget pullup 已发生，但上层仍认为 `usb ready = 0`

## vbus draw / 初期功耗门控

- `mtu3_gadget_vbus_draw()` 会记录 gadget 申报的 `mA`，并排队执行 `mtu3_vbus_draw_work()`
- `mtu3_vbus_draw_work()` 会通过 `usb_psy` 下发限流：
  - `0 mA`
  - `100 mA`
  - `unlimited`
- 在 `CONFIG_TC_CHARGER` 场景下，它使用：
  - `POWER_SUPPLY_PROP_CHARGE_CONTROL_LIMIT`
- 这条路径的意义不是普通充电限流，而是 USB device 初始连接阶段的功耗约束控制。
- 分析时必须关注：
  - `mtu->vbus_draw`
  - `mtu->is_active`
  - `mtu->suspend_flag`
  - `mtu->reset_flag`
  - `mtu->usb_start`
- 若场景涉及 “USB 插入初期功耗不能超过 25mW” 或类似的 PD/USB 认证要求，必须把 `vbus_draw` 视为关键检查点，而不能只看 role/gadget ready。

## 输出模板

```markdown
## 触发点
- 输入触发：<关键词/日志/事件>
- 首个命中函数：<function>

## USB 核心路径
- 角色应用链路：<call chain>
- 当前状态：<dr_mode/is_host/current role>
- vbus draw：<0mA / 100mA / unlimited + 触发条件>

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 约束

- 仅聚焦 MTU3 角色应用与核心行为，不跨域判因
- 若角色输入来自桥接层错误，转交 `transsion-extcon-usb-role-bridge`
- 若根因在 PD 侧附着/DR_SWAP 事件，转交 PD-TypeC skill
- 若 `cdp-block` 仍存在且怀疑前序 attach 或 BC1.2 worker 根本未进入，次域或主域可转交 `transsion-bc12-type-detect`
- 若问题涉及 USB 插入初期功耗、认证失败、或 `vbus_draw` 未按预期收敛，仍优先留在本 skill 内分析 `mtu3_core.c`
- 若日志明显是 MUSB（`using musb-hdrc` / `[MUSB]`），转交 `mtk-usb20-musb-otg-core`
- 若现象是 **OTG 已切 `USB_ROLE_HOST`、VBUS 已开、但无 xHCI / 无 `usb_add_hcd`**，或日志命中 **`ssusb_host_init_v2` / `mediatek,clk-mgr` / `platform_driver_register(xhci)`**，转交 **`mediatek-mtu3-xhci-host`**
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
