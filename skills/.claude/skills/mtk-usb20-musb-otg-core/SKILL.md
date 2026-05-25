---
name: mtk-usb20-musb-otg-core
description: “MTK-USB20-OTG: 分析MUSB的DRD/OTG/Host/Gadget路径，区分未识别OTG与已识别但上层未展示 | musb/otg/DRD/UHC/UDC/OTG识别/USB角色异常 | 当用户报告MTK设备OTG无法识别、USB角色切换失败时使用。Device模式枚举走mtu3-usb-device-core，Host模式xHCI走mediatek-mtu3-xhci-host”
---

# MTK USB20 MUSB OTG 核心

## 适用范围

聚焦 `drivers/misc/mediatek/usb/usb20`（MUSB 双角色）链路：
- Type-C / TCPC 事件进入后，如何切到 host/device
- `tran_extcon_usb` 到 `mt_usb role_sx_set` 的桥接
- MUSB host 枚举、hub/设备发现、gadget 停启

不包含：
- MTU3/XHCI（USB3）控制器内部实现
- 充电策略投票细节
- Android vold/framework 业务策略细节（仅做边界判断）

## 固定入口

优先从以下锚点开始：
1. `tran_extcon_usb`：`cur_dr(...) new_dr(...)`
2. `mt_usb`：`role_sx_set role X`
3. MUSB Host：`usb X-Y: ... using musb-hdrc` / `musb_hub_control`
4. MUSB Gadget：`musb_gadget_start/stop`、`musb_pullup`

对应代码入口：
- `usb20/usb20_host.c`：`mt_usb_host_connect()` / `mt_usb_host_disconnect()` / `do_host_work()`
- `usb20/musb_core.c`、`usb20/musb_host.c`、`usb20/musb_gadget.c`

## 快速判型：MUSB vs MTU3+XHCI

### 判定为 MUSB（usb20）常见日志
- `[MUSB]...`
- `usb ... using musb-hdrc`
- `mt_usb: role_sx_set role ...`
- `musb_hub_control`, `musb_stage0_irq`

### 判定为 MTU3+XHCI 常见日志
- `mtu3`, `ssusb`, `xhci-mtk`, `dwc3`
- `usb ... using xhci-hcd`

结论规则：
- 只要 host 枚举行明确是 `using musb-hdrc`，该次 OTG 主机链路按 MUSB 处理，不按 xHCI 处理。

## “未识别”与“已识别未上报”拆分

```text
MUSB OTG 诊断清单
- [ ] Type-C 是否到 SRC/OTG Plug in（事件源）
- [ ] extcon 是否从 NONE -> HOST（cur_dr/new_dr）
- [ ] mt_usb 是否执行 role_sx_set role 1（角色应用）
- [ ] 内核是否出现 using musb-hdrc（总线枚举）
- [ ] 是否继续出现 usb-storage/scsi/sdX 或 vold volume 事件（上层可见性）
```

判读建议：
- 前 4 步任一步失败：偏“OTG 未识别/未切到 host”
- 前 4 步成功但无块设备/卷管理事件：偏“已识别但未形成可展示存储入口”
- 若仅看到 `USB2.0 Hub`，说明识别到 Hub 级设备，不等价于已识别到 U 盘块设备

## 输出模板

```markdown
## 最终结论（先看这里）
- 拓展坞是否识别：<yes/no + 1 条关键日志>
- U 盘是否上报：<yes/no + 1 条关键日志>
- 问题分层：<OTG未识别 / Hub已识别但下游失败 / 已到上层但UI未展示>

## 控制器判型
- 判型结果：<MUSB(usb20) / MTU3+XHCI>
- 关键证据：<2-4 条日志锚点>

## 端到端时间线
- T0: Type-C/PD 事件
- T1: Extcon 角色变化
- T2: mt_usb 角色应用
- T3: Host 枚举（musb-hdrc/xhci-hcd）
- T4: 存储或上层可见性事件

## 边界判断
- OTG 是否识别：<yes/no + 证据>
- 是否已上报到足以展示 OTG 入口：<yes/no + 证据>

## 下一步
- 需要补抓日志：<usb-storage/scsi/vold/StorageManager 等>
- 需要转交：<extcon/PD/Android USB 配置 skill 或 none>
```

## 约束

- 必须先判型（MUSB 或 MTU3+XHCI），再给根因
- 结论必须绑定可检索日志锚点，不凭现象猜测
- 遇到 UI 未展示问题时，明确说明“内核识别层级到哪里为止”
- 回复结构必须“结论先行”：首段先回答“Hub是否识别、U盘是否上报”
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
