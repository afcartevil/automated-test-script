---
name: mediatek-mtu3-xhci-host
description: "MTK-MTU3-xHCI-Host: 分析SSUSB/MTU3在OTG下切USB Host(xHCI)路径及xhci驱动probe初始化顺序 | xhci/MTU3/ssusb_host_init/clk_mgr/Host模式/切Host无枚举 | 当用户报告MTK设备Host模式无xHCI、无枚举、xhci反复register时使用。Device模式走mtu3-usb-device-core，OTG走mtk-usb20-musb-otg-core"
funcType: "AI故障分析"
category: "驱动"
---

# MTU3 → xHCI Host：切换与初始化

## 适用范围

- **切 Host**：`usb_role_switch` / extcon / 调试接口 → **`ssusb_set_mode(..., USB_ROLE_HOST, ...)`** → workqueue 里完成 **gadget 停、端口选 Host、VBUS、（可选）xHCI 驱动绑定**。
- **xHCI 初始化**：**`drivers/misc/mediatek/usb/usb_xhci/xhci-mtk.c`** 中 **`xhci_mtk_probe()`**（及 `xhci_mtk_setup` 等 overrides）。
- ** glue 层**：**`drivers/usb/mtu3/mtu3_dr.c`**（角色切换）、**`mtu3_host.c`**（`ssusb_host_init` / `ssusb_host_init_v2`、`of_platform_populate`、`platform_driver_register`）。

不包含：TCPM/PD 角色协商细节、纯 gadget-only 栈、用户态 USB 存储与权限。

## 固定代码路径（本仓库）

| 模块 | 路径 |
|------|------|
| DRD 切换 | `kernel/kernel_device_modules-6.12/drivers/usb/mtu3/mtu3_dr.c` |
| Host 与 xHCI 衔接 | `kernel/kernel_device_modules-6.12/drivers/usb/mtu3/mtu3_host.c` |
| SSUSB 平台 probe | `kernel/kernel_device_modules-6.12/drivers/usb/mtu3/mtu3_plat.c` |
| xHCI 平台驱动 | `kernel/kernel_device_modules-6.12/drivers/misc/mediatek/usb/usb_xhci/xhci-mtk.c` |

## 1. 如何「切换到 xHCI」（语义说明）

「切换到 xHCI」在软件上 = **SSUSB IP 处于 Host 能力 + xHCI 驱动与 HCD 就绪**。具体有两层：

1. **MTU3/SSUSB 侧**：把 **DRD port0** 切到 **Host**（U2/U3 `HOST_SEL`）、必要时整 IP 上电、**OTG VBUS** 使能（对外供电）。
2. **xHCI 侧**：**`mediatek,mtk-xhci`**（或 `mtk-xhci-p1` / `mtk-xhci-p2`）子设备上的 **`xhci_mtk_probe()`** 成功 → **`usb_add_hcd()`** 等，Host 栈开始跑枚举。

二者先后顺序与是否 **重复注册 xHCI driver** 取决于 **`mediatek,clk-mgr`**（见下节）。

## 2. 入口与异步模型

- **`ssusb_set_mode(struct otg_switch_mtk *otg_sx, enum usb_role role, bool force)`**（`mtu3_dr.c`）  
  - 仅在 **`otg_sx->op_mode == MTU3_DR_OPERATION_DUAL`** 且 **`dr_mode == USB_DR_MODE_OTG`** 时向 **`otg_sx->wq`** 投递 work；否则直接 return。
  - **`USB_ROLE_HOST` 且 offload 未 ready** 等场景会 **提前 exit**（需结合 `offload_support` 日志）。

- Work 函数二选一（由 **`ssusb->clk_mgr`** 决定，DTS **`mediatek,clk-mgr`**，`mtu3_plat.c` 解析）：
  - **`ssusb_mode_sw_work`**：`INIT_WORK(..., ssusb_mode_sw_work)`  
  - **`ssusb_mode_sw_work_v2`**：`INIT_WORK(..., ssusb_mode_sw_work_v2)`

必须先看清 **`clk_mgr`**，否则会把「仅端口切换」与「整 IP 上下电 + 动态 register xhci」混成一条路径。

## 3. 两条切换路径（核心分流）

### 3.1 无 `mediatek,clk-mgr`：`ssusb_mode_sw_work`

目标 **`USB_ROLE_HOST`** 时典型顺序：

1. **`ssusb_set_force_mode(..., MTU3_DR_FORCE_HOST)`** —— U2 端口 **IDDIG** 强切 Host。
2. **`mtu3_stop(mtu)`** —— 停 **Device/gadget**。
3. **`switch_port_to_host(ssusb)`** —— **`ssusb_port0_switch`**（U2/U3 port0 **HOST_SEL**、时钟等）、**`toggle_opstate()`**。
4. **`ssusb_set_vbus(otg_sx, 1)`** —— **OTG 对外 VBUS**（regulator 存在时）。
5. **`ssusb->is_host = true`**。

**与 xHCI 的关系**：OTG **probe** 已执行 **`ssusb_host_init(ssusb, node)`** → **`of_platform_populate(parent_dn, ...)`** 创建 **mtk-xhci 子 platform_device**，模块 init 已 **`platform_driver_register(mtk_xhci_driver)`**，子设备出现即 **`xhci_mtk_probe()`**。  
动态切 Host 时 **通常不再** 走 **`ssusb_host_init_v2`**，主要是 **硬件侧 + 停 gadget**；xHCI 多数已在运行，除非被其它策略卸掉（需结合具体项目）。

### 3.2 有 `mediatek,clk-mgr`：`ssusb_mode_sw_work_v2`

切到 **`USB_ROLE_HOST`** 时（从非 Host 切过来）：

1. **`switch_port_to_on(ssusb, PHY_MODE_USB_HOST)`** —— **pm_runtime、时钟、PHY、`ssusb_reset`、上电状态机**等（见 `switch_port_to_on()`）。
2. **`ssusb_host_init_v2(ssusb)`** —— 见下一节。
3. **`ssusb->is_host = true`**，**`mtu3_set_speed(..., max_speed_host)`**。

离开 Host 时对称：**`ssusb_host_exit_v2()`** 内会 **`platform_driver_unregister(ssusb->xhci_pdrv)`** 等（与 `mtu3_host.c` 实现一致）。

## 4. xHCI 如何被「挂上」：init vs init_v2

### 4.1 `ssusb_host_init()`（probe 阶段，OTG 共用）

- **`ssusb_host_setup(ssusb)`**：**`ssusb_host_enable()`**（清 **`SSUSB_IP_HOST_PDN`**、配置 U2/U3 口为 Host 等）、**`ssusb_set_force_mode(HOST)`**、**`ssusb_set_vbus(..., 1)`**。
- **`of_platform_populate(parent_dn, NULL, NULL, parent_dev)`** —— 实例化 **子节点 `mediatek,mtk-xhci`** 设备。
- **`ssusb_get_platform_driver` / `ssusb_get_host_rscs`** —— 缓存 **`xhci_pdrv`**、**`host_base`**（`mac` 资源）等。

### 4.2 `ssusb_host_init_v2()`（clk-mgr 动态 Host）

- **`ssusb_host_setup(ssusb)`** —— 同上。
- **`ssusb_host_register(ssusb, true)`** → **`platform_driver_register(ssusb->xhci_pdrv)`** —— 对已在 **子节点 pdev** 上解析到的 **`mtk_xhci_driver`** 再注册，使 **xHCI 与 HCD 绑定到 probe**。
- **`ssusb_get_host_rscs(ssusb)`** —— 映射 **host 寄存器**。

对称：**`ssusb_host_exit_v2()`** → **`ssusb_host_register(ssusb, false)`** → **`platform_driver_unregister`**。

**`xhci_pdrv` 来源**：`ssusb_get_platform_driver()` 遍历 **父节点子节点**，匹配 **`mediatek,mtk-xhci` / `mtk-xhci-p1` / `mtk-xhci-p2`**，从已 **`pdev->dev.driver`** 的 **`platform_driver`** 取指针（`mtu3_host.c`）。

## 5. `xhci_mtk_probe()` 初始化要点（`xhci-mtk.c`）

典型顺序（与 `xhci_mtk_probe` 源码一致，细节以分支为准）：

1. **资源**：`xhci_mtk_vregs_get`、`xhci_mtk_clks_get`；IRQ **host** / **wakeup**（可选 name）。
2. **PHY**：`devm_of_phy_optional_get`（可选）。
3. **DTS 能力位**：`usb3-lpm-capable`、`mediatek,u2p-dis-msk` / `u3p-dis-msk`、`rx-fifo-depth` 等。
4. **PM**：`pm_runtime_enable`、`pm_runtime_get_sync`；**regulator_bulk_enable**、**clk_bulk_prepare_enable**。
5. **复位**：`device_reset_optional`。
6. **HCD**：`usb_create_hcd(driver, ...)`；映射 **`mac`**（及可选 **`ippc`**）到 **`hcd->regs`** / **`mtk->ippc_regs`**。
7. **xHCI 结构**：`hcd_to_xhci`、`xhci->main_hcd`、`allow_single_roothub`；可选 **`mediatek,usb-offload`** → **`xhci->vendor_ops`**。
8. **上线**：**`usb_add_hcd(hcd, irq, IRQF_SHARED)`**；若双 roothub，**`usb_create_shared_hcd` + `usb_add_hcd(shared)`**。
9. **唤醒 IRQ**：`dev_pm_set_dedicated_wake_irq_reverse`（若存在）。
10. **收尾**：`pm_runtime_put_autosuspend`、`pm_runtime_forbid`；`snd_usb_register_platform_ops`、trace 等。

**remove**：`xhci_mtk_remove` → **`xhci_mtk_halt_and_cleanup`** → **`usb_remove_hcd`** → 关 clk/ldo。

## 6. DTS 与排查锚点

- **`mediatek,clk-mgr`**：是否走 **`ssusb_mode_sw_work_v2` + `ssusb_host_init_v2`**；与 **仅 populate** 路径行为不同。
- **子节点**：`mediatek,mtk-xhci` / `mtk-xhci-p1` / `mtk-xhci-p2` 必须与 **`ssusb_get_platform_driver`** 匹配逻辑一致。
- **日志关键词**：`ssusb_set_mode`、`ssusb_mode_sw_work`、`ssusb_mode_sw_work_v2`、`switch_port_to_host`、`switch_port_to_on`、`ssusb_host_init` / `ssusb_host_init_v2`、`xhci_mtk_probe`、`usb_add_hcd`、`register host driver`。

## 转交

- 角色来自 **TCPC/extcon** 但未到 **`usb_role_switch_set_role`**：优先 **`transsion-extcon-usb-role-bridge`**。
- 通用 DRD/gadget/cdp-block：**`mtu3-usb-device-core`**（本 skill 专注 **Host↔xHCI** 衔接）。
- 跨域总入口：**`power-usb-cross-stack-triage`**。

## 输出模板

```markdown
## 平台与配置
- DTS：`mediatek,clk-mgr` = <yes/no>
- dr_mode：OTG / HOST / PERIPHERAL

## 切换路径（Host）
- 实际 work：ssusb_mode_sw_work / ssusb_mode_sw_work_v2
- 是否调用：ssusb_host_init_v2 / 仅 switch_port_to_host

## xHCI 状态
- mtk-xhci 子节点是否 populate / xhci_pdrv 是否非空
- xhci_mtk_probe 是否成功、usb_add_hcd 是否返回 0

## 结论与下一步
- 根因层级：<MTU3 端口 / Host 驱动注册 / xhci probe>
- 下一步文件/函数：<path>
```
