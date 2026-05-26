---
funcType: "AI自动化适配"
category: "驱动"
---
﻿---
name: tp-adapt-dws-pin
description: Aligns and audits Mediatek/Transsion touch-panel DWS pins against TP GPIO lines in DTS (RST/INT/AVDD/VDDI modes and pulls), and enforces identical DWS across all project copies. Use when modifying or checking TP DWS, GPIO mismatch with *_touch.dtsi, TP bring-up, or porting touch under arch/arm64/boot/dts/mediatek/tp.
disable-model-invocation: true
---

# MTK/Transsion TP DWS 引脚修改与一致性检查

根据项目dts中的tp gpio引脚配置，配置对应的dws引脚。

TP RST一般为下拉低电平输出、TP INT为中断上拉输入、TP AVDD为下拉低电平输出、TP VDDI为下拉低电平输出。

同一项目内 **`vendor/mediatek/proprietary` 下三处 DWS 参考路径**（见下文表格）的配置需一致。

TP 的 DTS 一般在 **`arch/arm64/boot/dts/mediatek/tp/`** 目录下（`mediatek/tp/*_touch.dtsi` 等，由板级 `dts/dtsi` include）。

## 从 DTS 抽取 TP 线名与 GPIO

1. 打开该机型的 touch 片段（常见：`mediatek/tp/<proj>_touch.dtsi`，或由板级 `dts/dtsi` include）。
2. 在 TP 控制器节点及其 `pinctrl` 里定位：`reset-gpios`、`irq-gpios` / `interrupts`、`vdd-supply` / `vio-supply`（若由 GPIO 模拟电源脚则会出现在 vendor 节点或 regulator/gpio）。
3. 记下每条线对应的 **`&pio <n>`（或 PMIC GPIO）编号** 与 **有效电平**（`GPIO_ACTIVE_HIGH` / `GPIO_ACTIVE_LOW`），后续必须与 DWS 网表/net 映射到同一 GPIO 号。

## DWS 侧电气约定（与 TP 常见走线对齐）

按硬件与驱动惯例配置 DWS 行（具体字段名随 Meta/DWS 工具版本略有差异，以当前表格列名为准）：

| 信号 | 一般为 | 说明 |
|------|--------|------|
| **TP RST** | **下拉、低电平输出** | GPIO **输出**；默认/休眠态与复位极性一致时多为 **输出低**；**下拉**与 idle 态一致，避免浮空。与 DTS `reset-gpios` 的有效电平一致。 |
| **TP INT** | **中断、上拉输入** | 配置为 **GPIO 输入** / **EINT**（若表格单列为中断类型则选中断）；**上拉**与 TP 模组中断开漏/OC 输出匹配。与 `irq-gpios`、`interrupt-parent` 一致。 |
| **TP AVDD** | **下拉、低电平输出** | 若该电源由 GPIO 控制：GPIO **输出**，idle/off 常为 **低** + **下拉**（以原理图为准）。 |
| **TP VDDI** | **下拉、低电平输出** | 同上，与 DSI/IO 电轨开关 GPIO 一致。 |

若某机型电源由 PMIC LDO solely 供电、无 GPIO，则 **不要在 DWS 里虚构 TP AVDD/VDDI GPIO**；仅核对 DTS `*-supply` 与硬件一致。

## 三处 DWS 来源一致性（必做）

在同一 Mediatek `vendor` 树内，优先按下述 **三处参考路径** 核对；`<platform>` / `<project>` 替换为实际平台与项目代号，平台名称例如mt6789、项目名称例如x6870_h781。**不同 BSP 分支目录可能略有出入，以仓库为准**（路径统一写为正斜杠）。

| # | 角色 | 参考路径 |
|---|------|----------|
| 1 | DCT 工具侧 DWS（主编辑源之一） | `vendor/mediatek/proprietary/tools/dct/dws/<platform>/<project>/<project>.dws` |
| 2 | Bootable Preloader custom 导出 | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/dct/dws/codegen.dws` |
| 3 | Preloader custom kernel DCT 导出 | `vendor/mediatek/proprietary/preloader/custom/<project>/kernel/dct/dct/codegen.dws` |

**规则**：上述每一处中，**同一 net（TP_RST / TP_INT / TP_AVDD / TP_VDDI 等）的 MODE、DIR、PULL、EINT/GPIO 编号必须与 DTS 一致，且三份文件之间逐行一致**。若只改一处会导致打包漏同步、GPIO 号漂移。

**实操**：对表中三个文件（或同路径命中到的等价文件）做 **diff**；并用项目代号 + 关键字（如 `TP_RST`、`CTP`、`TOUCH`）在仓库内补充搜索，避免存在第四条同名副本未同步。

## 与 DTS 对齐的检查清单

- [ ] **GPIO 编号**：DTS `gpios = <&pio N …>` 的 **N**（或 PMIC GPIO）与 DWS 该 net 的最终 GPIO **完全相同**。
- [ ] **功能模式**：TP 线为 **GPIO**，未被 UART/SPI/I2C 等复用占用。
- [ ] **方向**：RST/电源 GPIO 为 **输出**；INT 为 **输入（中断）**。
- [ ] **上下拉**：RST/AVDD/VDDI 为 **下拉 + 低电平输出**（按上文约定）；INT 为 **上拉输入**。
- [ ] **与 pinctrl 一致**：`*_default` / `*_sleep` 中同一脚的模式不与 DWS 意图冲突；以开机生效路径为准。
- [ ] **三份 DWS**：`tools/dct/dws/<platform>/<project>/<project>.dws` 与两处 `codegen.dws`（bootable preloader、preloader/kernel DCT）中 TP 相关 net 一致。
- [ ] **变更记录**：注明修改的 DWS 文件名、net 名、修改前后 MODE/PULL/DIR。

## 输出结论模板（分析/评审时使用）

```markdown
## TP DWS 核对结论
- DTS：`path/to/*_touch.dtsi`（RST/INT/AVDD/VDDI 引脚摘录）
- DWS：列出已核对的三处路径及文件
- 一致性：一致 / 不一致（列出差异 net）
- 风险：与原理图或模组手册不符项
```

## 常见误判

- **仅改 DTS 未改 DWS**：休眠恢复后 pinmux 正确但 Pad 默认电气不对，导致漏电、误中断或复位异常。
- **只改一处 custom**：另一处 `custom` 仍引用旧 GPIO，量产工具与内核不一致。
- **INT 无上拉**：模组开漏中断浮空，表现为随机中断或无法唤醒。

## 额外资源

- AI 物理键与 DWS 通用检查思路可参考同目录 skill：`transsion-ai-key-dts-adapt`（gpio 与 DWS 对齐原则相通）。
