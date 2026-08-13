---
name: mtk-adapt-pillar2-router
description: MTK 适配柱 2 入口：消费 Pillar 2 Parameter Inputs 与柱 1 Handoff，分流到 mtk-adapt-template-basic-charging-capability 及按需 bridge/migrate skill，输出 Pillar 2 Handoff。由 mtk-adapt-template-router 调度；含 tc_charger、tc_pe5、support_alg、OTG 等参数与老树 DTSI 迁移闸门。
---

# 柱 2 — 基本充电能力参数入口

## 用途

柱 2 **唯一入口**。处理 `tc_charger_lk.dtsi`、`tc_charger.dtsi`、`tc_pe5.dtsi`、`support_alg`、OTG、温区、MIVR、EOC、USB2 眼图等**基本充电能力参数**。

不负责：器件脚位首次定义（柱 1）、客制化 RULE/SM40（柱 3）。

## 何时进入

- **`mtk-adapt-template-router`** 调度且 `pillar2_parameters: required`
- 用户明确「仅做参数适配」且 **已具备柱 1 器件结论或用户确认可跳过柱 1**

进入前：
1. **`Read` `transsion-aosp-path-conventions`**
2. 确认已消费 **Pillar 1 Handoff**（或用户书面确认器件事实）

## 主下游

| 场景 | 下游 skill |
|------|------------|
| 基本充电能力参数（默认） | **`mtk-adapt-template-basic-charging-capability`** |
| 工程路径 / DTSI include / DWS / bootloader mk 迁移 | **`tran-projects-config-migrate-dtsi-dws`** |

`tc_charger_lk.dtsi` **强约束**（预充 2.5 V、AC 2 A、非标 1.2 A、`temp-t4` 56 °C 等）以 basic-charging skill 正文为准。

## 强制 Read（bridge / migrate 闸门）

| 场景 | 必须先 Read |
|------|-------------|
| 老树含 **`tran_battery` / `tran,chg_fun`**，或 **`jeita_*_chg_cur` / `pcb_*`** 迁入 **`&charger`** | **`transsion-tran-battery-to-tc-charger-dtsi`** 全文 |
| 老树含 **`&pe5` / `mtk_pe50.dtsi` / `mediatek,charger,pe5`**，新树写 **`tc_pe5.dtsi`** | **`transsion-pe5-migrate-dual-cp-k612`** |
| DTSI↔驱动语义、OTG、`tran_otg`、`water_detect`、`support_alg`、`extcon_usb` 等 | **`transsion-charger-dtsi-driver-bridge`**（按需；与上行 **并存，不互相替代**） |
| 平台版本跃迁（可选） | **`mtk-adapt-upgrade-platform-delta-table`** |

`required_bridge_skills` 来自输入包或 Inventory 时 **必须逐项 Read** 后再落盘。

## 硬件静态 vs 策略参数

- **可对读直拷**（经用户知情）：CP 从片 I2C、与老树一致的 IRQ GPIO 等 BOM 静态项。
- **须 bridge / 用户确认**：温区策略、PE5 `*_curlmt` 语义（老栈可 ×2、新栈不 ×2）、5.10→6.12 节点别名 — **禁止静默臆测等价**。

## 最小输入契约

- 柱 1 器件事实（或用户确认跳过）
- 参数变更目标：`tc_charger_lk_targets`、`tc_charger_dtsi_targets`
- `legacy_nodes`、`required_bridge_skills`（升级场景）
- `tc_charger_lk.dtsi` 目标相对路径（建议用户直接给出）

## 输出契约

输出 **Pillar Handoff Output**（`pillar: 2`），须含：
- 参数落点、**`source` / `convert` / `[REVIEW]`** 标注
- 已 Read 的 bridge skill 摘要
- 下一柱建议（若柱 3 `required`）

## 边界

- 本 router **不直接改文件**。
- KPOC / 工模 / 其它客制化 → **`mtk-adapt-pillar3-router`**（不得在本柱冒充柱 3 落盘）。
