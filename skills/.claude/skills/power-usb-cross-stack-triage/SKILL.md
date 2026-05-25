name: power-usb-cross-stack-triage
description: “MTK-Transsion-Power/USB跨模块分诊: 对Power/USB跨模块问题做总分诊与分流，自动路由到PD-TypeC/TCPC/BC1.2/charger/extcon/MTU3/battery-gauge/xHCI等skill | USB/PD/充电/插拔/TypeC/OTG | 当用户报告现象跨域、根因不清的Power/USB联调问题时使用——本skill为路由入口，不深入单域分析”
---

# Power/USB 跨栈分诊

## 适用范围

本 skill 是总分诊器，不做单域深挖实现。

可分流到以下 skill：
- `transsion-tcpc-adapter`
- `transsion-bc12-type-detect`
- `transsion-dcp-fastcharge-probe`
- `transsion-pe5-vi-tuning`
- `transsion-charger-orchestrator`
- `transsion-batt-high-temp-low-cv-eoc`
- `transsion-wireless-bypass-fan`
- `mtk-battery-gauge-stack`
- `transsion-extcon-usb-role-bridge`
- `mtk-usb20-musb-otg-core`
- `mtu3-usb-device-core`
- `mediatek-mtu3-xhci-host`（OTG 切 Host、`ssusb_host_init`/`init_v2`、**`xhci_mtk_probe`**）
- `mediatek-pd-typec-protocol-6-12`

固定观察点：
- PD/Type-C 入口：`kernel/kernel_device_modules-6.12/drivers/misc/mediatek/typec/tcpc/tcpci_alert.c`
- Transsion TCPC 适配：`kernel/kernel_device_modules-6.12/drivers/power/supply/transsion/tc_tcpc.c`
- BC1.2/type detect：`kernel/kernel_device_modules-6.12/drivers/power/supply/transsion/tc_chg_type_det.c`
- 充电主控：`kernel/kernel_device_modules-6.12/drivers/power/supply/transsion/tc_charger.c`
- 角色桥接：`kernel/kernel_device_modules-6.12/drivers/misc/mediatek/extcon/tran_extcon_usb.c`
- MTU3 核心：`kernel/kernel_device_modules-6.12/drivers/usb/mtu3/mtu3_dr.c`
- MTU3 Host / xHCI：`mtu3_host.c`、`usb_xhci/xhci-mtk.c`（见 **`mediatek-mtu3-xhci-host`**）

## 分流规则

先按主链分层识别问题落点：

1. 原生 TCPC / PD 协议层
   - 命中 `CC_ALERT` / `ps_change` / `RX_STATUS` / `PD` / `policy engine`
   - 分流到 `mediatek-pd-typec-protocol-6-12`
   - 若额外命中 `CC_Alert 1/0` / `1/1` / `2/1` 高频反复：
     - 在结论里标注“外部链路不稳（优先怀疑拓展坞）”
2. Transsion TCPC 适配层
   - 命中 `tc_tcpc` / `TCP_NOTIFY` / `TC_TYPEC_` / `TC_PD_`
   - 分流到 `transsion-tcpc-adapter`
3. BC1.2 / type detect 层
   - 命中 `bc12` / `BC1.2` / `cdp-block` / `usb ready` / `is_usb_rdy` / `port stat`
   - 分流到 `transsion-bc12-type-detect`
3.1 充电图标不出现（online 抖动）专项
   - 命中 `mtk_battery_external_power_changed ... online:0` / `online:1` 反复切换
   - 命中 `tc_detect_do_bc12 ... psy_type:Unknown, usb_type:Unknown`
   - 命中 `mtk-extcon-usb ... online=0, type=0` 与 `online=1` 交替
   - 主域分流到 `transsion-bc12-type-detect`
   - 次域按证据追加：
     - `TCPC-TYPEC:[CC_Alert]` 高频抖动 -> `mediatek-pd-typec-protocol-6-12`
     - `tc_chg_tcpc_notifier_call 12/7` 高频翻转 -> `transsion-tcpc-adapter`
4. DCP 后快充探测层
   - 命中 `support_alg` / `pe5` / `pd` / `hvdcp20` / `tc30` / `pe20` / `tc_algo_protocol_process` / `tchg_alg_is_algo_ready` / `data->running_algo`
   - 或命中 PE5 内层：`tfcp_adapter` / `pd_adapter` / `hvdcp30_adapter` / `RFC_HANDSHAKE` / `support_ta` / `authenticate_ta` / `PE50_RFC` / `PE50_PPS` / `PE50_QC3`
   - 分流到 `transsion-dcp-fastcharge-probe`
4.1 PE5 调压调流 / 机种 DTS 层（协议已选定之后）
   - 命中 `tc_pe50` / `pe50_vta_init` / `pe50_ita_init` / `idvchg_ss_*` / `support_spec` / `vta_cap_*` / `step_ffc_level` / `tta_*` / `tbat_*` / `PE50_ALGO` / `vta_setting` / `ita_setting`
   - 分流到 `transsion-pe5-vi-tuning`（需对应机种 `tc_pe50.dtsi` 或 `pe5` 节点）
4.2 客制化特性入口（先主控后协议）
   - 命中 `support_enhance_mode` / `set pid target temp` / `ALG_ADAPTER_CAPACITY`
   - 命中 `bypass_charger` / `wait_protocol_work` / `BYPASS_CHG_VOTER` / `BYPASS_V20_ENABLE`
   - 命中 `chgspeed_ctl` / `TRAN_MULTI_SPEED_TRAVEL` / `speed_owner_old`
   - 主域先分流到 `transsion-charger-orchestrator`
   - 若争议点是 PE5 已选型后的参数生效，追加次域 `transsion-pe5-vi-tuning`
   - 若争议点是 DCP 后外层算法竞选，追加次域 `transsion-dcp-fastcharge-probe`
4.3 无线旁路入口（磁吸风扇）
   - 命中 `support_magnetism_fan_check` / `support_magnetism_fan_bypass` / `magnetism_fan_bypass_aicr`
   - 主域分流到 `transsion-wireless-bypass-fan`
   - 若同时命中有线旁路锚点（`bypass_charger` / `BYPASS_CHG_VOTER`），主域改为 `transsion-charger-orchestrator`，无线旁路作为次域
4.4 高温低 CV 满充 / 不报百（CHGSTAT + 停充）
   - 命中 `tc_high_temp_lock_uisoc_check` / `is_low_cv_status` / `smooth_soc_full_vol` / `CHG_BAT_HT_EOC_STATUS` / `high temp charger full` / `VOTER_BATT_HIGH_TEMP_EOC`
   - 主域分流到 `transsion-batt-high-temp-low-cv-eoc`（实现仍在 `tc_charger.c`，与 `transsion-charger-orchestrator` 重叠时以专项 skill 为准）
   - 若争议在 **电池表 CV/JEITA 为何压低**，次域可补 `transsion-charger-orchestrator` 的 JEita 更新链或机种 `tc_charger` DTS
5. 充电主控编排层
   - 命中 `tc_charger` / `vote` / `plug in` / `plug out` / `charging disable` / `hiz`
   - 分流到 `transsion-charger-orchestrator`
6. Extcon / role bridge 层
   - 命中 `tran_extcon_usb` / `role switch` / `host/device` / `DR_SWAP`
   - 分流到 `transsion-extcon-usb-role-bridge`
7. USB 控制器执行层
   - 命中 `[MUSB]` / `musb-hdrc` / `mt_usb` / `usb20` / `musb_hub_control`
   - 分流到 `mtk-usb20-musb-otg-core`
   - 命中 `mtu3` / `ssusb` / `xhci` / `dwc3` / `enumeration` / `dr_mode`
   - 分流到 `mtu3-usb-device-core`
   - 命中 `ssusb_host_init` / `ssusb_host_init_v2` / `ssusb_mode_sw_work_v2` / `mediatek,clk-mgr` / **Host 已选但无 `usb_add_hcd` / xHCI 未 probe**
   - 分流到 **`mediatek-mtu3-xhci-host`**
8. Battery / gauge 层
   - 命中 `battery` / `SOC` / `gauge` / `coulomb` / `fgauge`
   - 分流到 `mtk-battery-gauge-stack`

多域同时命中时，优先级为：
- PD-TypeC -> TCPC adapter -> BC1.2 -> DCP fastcharge probe ->（PE5 已选型后）`transsion-pe5-vi-tuning` -> Extcon -> MUSB/MTU3 -> tc_charger -> Battery

## 分诊原则

- 先判断事件源在哪一层首次失真，再决定主域 skill。
- `tc_chg_type_det.c` 与 `tc_charger.c` 必须拆开判断，不能统称为 charger 问题。
- `tran_extcon_usb.c` 与 `mtu3_dr.c` 必须拆开判断，一个是角色桥接层，一个是控制器执行层。
- 若问题表现为“PD 没开始 / APDO 迟迟不来”，先检查 `pd_put_cc_attached_event()` 是否被 `TYPEC_RT_TIMER_PD_WAIT_BC12` 拦截，而不是直接假设 PD policy engine 故障。
- `cdp-block` 是跨域锚点：
  - 若 `is_usb_rdy()` 长时间为 0，主域通常是 `transsion-bc12-type-detect`
  - 次域通常是 `mtu3-usb-device-core`
- `PD_WAIT_BC12` 是另一个跨域锚点：
  - 若 `USB_TYPE_UNKNOWN` 或 `tfcp_adapter det_done` 未完成，主域常是 `transsion-bc12-type-detect`
  - 次域常是 `mediatek-pd-typec-protocol-6-12`
- `vbus_draw` / USB 初期功耗也是跨域锚点：
  - 若问题是 USB 插入初期功耗超标、认证不通过、或 device 初期被限制为 0mA/100mA，主域常是 `mtu3-usb-device-core`
  - 次域可能是 `mediatek-pd-typec-protocol-6-12` 或 `transsion-bc12-type-detect`
- `support_alg` vs `support_ta` 是快充分诊的关键锚点：
  - `support_alg`（`tc_charger` 节点）决定 **注册哪些 `tchg_alg` 以及 `tc_algo_protocol_process()` 的外层遍历顺序**
  - `support_ta`（`tc_pe5` 节点）只在 **`running_algo == pe5`** 时决定 **PE5 内 `tfcp_adapter` / `pd_adapter` / `hvdcp30_adapter` 的优先级**
- 客制化与协议并存时，先判“特性入口是否命中”：
  - 已命中特性入口：主域通常是 `transsion-charger-orchestrator` 或 `transsion-wireless-bypass-fan`
  - 未命中特性入口但命中 `start_algo/set_ta_vchr`：主域通常是 `transsion-dcp-fastcharge-probe`
- 若问题描述只说“USB/充电异常”但没有日志锚点，优先补齐首个跨层事件：
  - `CC_ALERT`
  - `TC_TYPEC_*`
  - `TYPEC_RT_TIMER_PD_WAIT_BC12`
  - `check CDP block`
  - `ssusb_set_mode`
  - `mtu3_gadget_vbus_draw`
  - `tc_charger_plug_in`
- 若问题描述是“插线后概率性不出充电图标”，优先补齐：
  - `TCPC-TYPEC:[CC_Alert]`
  - `CC_Alert 1/0`、`1/1`、`2/1` 是否出现及频次
  - `[TC_TCPC] ... USB Plug in/out`
  - `tc_detect_do_bc12:attach:* psy_type:* usb_type:*`
  - `tc_detect_get_charger_status ... online:x,y`
  - `mtk_battery_external_power_changed ... online:*`

图标抖动场景优先怀疑序：
- 拓展坞（dock/hub）CC 侧不稳定
- C 口脏污/接触不良
- 线材不佳
- 充电器或对端端口不稳

## 跨栈时间线模板

跨域问题统一输出：

```text
Cross-Stack Timeline
- T0: 现象触发（日志 / 事件 / 用户症状）
- T1: PD-TypeC 原生事件（`tcpci_alert()` / `CC_ALERT` / `ps_change`）
- T2: Transsion 适配事件（`tc_tcpc.c` 的 `TC_TYPEC_*` / `TC_PD_*`）
- T3: 角色或检测分支
  - 角色链：`tran_extcon_usb` -> `mtu3` / `musb`
  - （Host / U 盘等）`ssusb_set_mode(HOST)` -> `ssusb_mode_sw_work(_v2)` -> `ssusb_host_init(_v2)` -> **`xhci_mtk_probe` / `usb_add_hcd`**（见 **`mediatek-mtu3-xhci-host`**）
  - 检测链：`tc_chg_type_det` -> BC1.2 / charger ops
- T4: 充电主控响应（`tc_charger` / vote / plug in-out）
- T4.1: 快充算法外层（`support_alg` -> `tc_algo_protocol_process()` -> `data->running_algo`）
- T4.2: （可选）PE5 内层（`support_ta` -> `pe50_is_ta_rdy()` / `authenticate_ta()` / `PE50_*`）
- T5: Battery / UI / 外显结果（如有）
```

## 输出模板

```markdown
## 最终结论（先看这里）
- 控制器路径：<MUSB / MTU3+XHCI / 其他>
- 识别状态：<未识别 / 已识别但未桥接 / 已桥接但未执行 / 已执行且已上报>
- 一句话原因：<1 行，必须带日志锚点关键词>

## 分诊结果
- 主域：<skill>
- 次域：<skill list 或 none>

## 分流依据
- 命中关键词：<keywords>
- 分流原因：<1-2 行>

## 端到端时间线
- T0: ...
- T1: ...
- T2: ...
- T3: ...
- T4: ...
- T5: ...

## 下一步
- 第一深挖 skill：<skill name>
- 追加转交：<if needed>
```

## 约束

- 不替代领域 skill，只做路由与汇总
- 证据不足时，先补一个明确日志锚点再深挖
- 结论必须可回溯到具体事件或日志
- 回复结构必须“结论先行”：第一段直接给最终判断，再给证据与时间线
- 输出时必须明确主域与次域，不能只说“跨域问题”
- 若命中客制化特性入口，输出中必须带 A/B/C 失败分层：A 资格门控、B 执行路径、C 验收路径
- 若主域是 `transsion-bc12-type-detect`，必须交代 `cdp-block` 是否参与门控
- 若主域或次域涉及 PD，必须交代 `CC_ATTACHED` 是否已真正入队，还是仍被 `PD_WAIT_BC12` 门控
- 若主域是 `transsion-extcon-usb-role-bridge`，必须交代角色是否已成功下发到 MTU3/MUSB
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
- 任一协议（RFC/PD/PPS/QC/HVDCP/TC30/PE 等）出现握手失败时，必须先核对“对端是否支持该协议”；不能把失败日志直接当作链路不稳定证据
- 若对端能力未知，必须显式标注“能力未知，当前仅能判定协商未成功”
