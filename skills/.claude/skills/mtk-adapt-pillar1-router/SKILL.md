---
name: mtk-adapt-pillar1-router
description: MTK 适配柱 1 入口：消费 Adaptation Input Packet 的 Pillar 1 Device Inputs，按器件类别分流到 mtk-adapt-template-device-charger-ic、pd-ic、charge-pump、gauge，输出 Pillar 1 Handoff。由 mtk-adapt-template-router 调度；单做柱 1 时可直进本 skill。
---

# 柱 1 — 器件适配入口

## 用途

柱 1 **唯一入口**。接收 `Pillar 1 Device Inputs`，按器件类别 **`Read` 下游 device 模板**，输出器件事实供柱 2 使用。

不负责：JEITA、温区、电流表、客制化开关、柱 2/3 参数。

## 何时进入

- **`mtk-adapt-template-router`** 调度且 `pillar1_device: required`
- 用户明确「仅做器件适配」且已具备 Scope / Evidence / Pillar 1 Inputs

进入前：改码路径先 **`Read` `transsion-aosp-path-conventions`**。

## 二级分流

| 器件类别 | 下游 skill |
|----------|------------|
| charger IC | `mtk-adapt-template-device-charger-ic` |
| PD IC / TCPC | `mtk-adapt-template-device-pd-ic` |
| charge pump | `mtk-adapt-template-device-charge-pump` |
| gauge | `mtk-adapt-template-device-gauge` |

多器件并存时：**按上表逐项 Read**，handoff 中分列各器件结论。

## 最小输入契约

- `project_full`、平台、AOSP 根（或可由 Evidence 推导）
- 器件型号 + 类别（必填）
- 硬件连线摘要：bus、addr、irq、enable、电源
- 含 **TFCP / `protocol_ta.dtsi`** 时：查平台 dts 的 `protocol_ta` **`i2cN`** 与 **`scl-gpio-id` / `sda-gpio-id`**，并在 kernel DWS + preloader `codegen.dws` 写 **`TRAN_CHGPUMP_SCL_PIN` / `TRAN_CHGPUMP_SDA_PIN`**（见 charge-pump §1.6.1、`tran-projects-config-migrate-dtsi-dws`）

缺必填项 → `status: blocked`，列出缺口，**不推断落盘**。

## 输出契约

输出 **Pillar Handoff Output**（`pillar: 1`），须含：
- 各器件型号、I2C、IRQ、GPIO、DWS、ProjectConfig / LK / PL 宏落点
- 选用的 device skill 及原因
- 缺失项与 `[REVIEW]` 假设

**可选收尾**：对新旧 `vendor/transsion/projects/<project_full>/ProjectConfig.mk` **diff**，查未被本次覆盖的游离宏（同 Inventory 块 D.2）。

## 升级（老→新）

从老树 dtsi / `compatible` / I2C **归纳器件列表** → 按上表 Read 各 device 模板，与绿场 **同一套** 落盘规则。器件清单由 `mtk-adapt-upgrade-branch-orchestrator` / Inventory 填入输入包。

## 边界

- 本 router **不直接改文件**；落盘由下游 device skill 指导。
- 柱 2 参数、柱 3 客制化 → **`mtk-adapt-pillar2-router`** / **`mtk-adapt-pillar3-router`**。
