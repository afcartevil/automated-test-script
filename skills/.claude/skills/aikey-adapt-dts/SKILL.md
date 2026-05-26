---
funcType: "AI自动化适配"
category: "驱动"
---
﻿---
name: aikey-adapt-dts
description: Guides Transsion/MTK AI physical key (Ai_Key) bring-up in device tree under arch/arm64/boot/dts/mediatek/tp touch dtsi files using gpio-keys with linux,input code and GPIO, plus DWS pin/GPIO checks and optional PMIC key remapping. Use when adapting a new project for AI key, KEY 605 / Ai_Key no event, migrating from a reference *_touch.dtsi, or when the user mentions AI key、Ai_Key、gpio-keys、DWS、linux,code 605 with TP DTS.
---

# Transsion AI Key（Ai_Key）DTS 适配

AI key 机型适配在 **内核侧常见三件事**：绑定 **Linux 输入键值**、在 DTS 里写好 **GPIO（或 PMIC 按键）**，并在 **DWS（引脚/GPIO 数据库）** 里保证该脚已被正确配置为 **GPIO 输入** 且与原理图一致。Touch 片段写在 **`arch/arm64/boot/dts/mediatek/tp/*_touch.dtsi`**；DWS 源文件多在 **Meta / vendor 整机配置仓库**（本 kernel-only 工程里可能没有 `.dws`，适配时仍需到对应项目里查）。

## DWS 配置检查（必做）

gpio-keys 方案下，**DTS 里的 `&pio N` 必须与 DWS 中该 net/引脚最终映射的 GPIO 编号一致**，且引脚功能不能占成外设模式。

| 检查项 | 说明 |
|--------|------|
| **GPIO 号对齐** | 原理图 net → DWS 行 → 导出/代码里的 GPIO 号，与 `gpios = <&pio N ...>;` 中 **N** 一致（含跨平台「GPIO 别名」时勿抄错机型的号）。 |
| **模式为 GPIO** | AI key 脚在 DWS 中应为 **GPIO**（或等价「普通 IO」），**不能**仍为 SPI/I2C/UART 等复用功能，否则内核即使用对编号也无法当按键线用。 |
| **输入方向与默认电平** | 配置为 **输入**；**上拉/下拉** 与原理图空闲态一致，并与 DTS 里 **active high/low**（`gpios` 第三个 cell）一致，否则表现成常按、不弹起或抖动。 |
| **驱动能力 / SMT** | 按键线一般按硬件指南设默认驱动；若有 **slew / ESD / debounce** 相关选项，按平台指引与硬件核对。 |
| **与 pinctrl 一致** | 若某功能在 **kernel dtsi 的 pinctrl** 里把同一脚拉成别的 mode，会与 DWS 意图冲突；以 **最终开机的有效配置** 为准做二选一。 |

PMIC 按键路径（`&mt6366keys`）：在对应 PMIC 按键 **DWS / 矩阵** 里确认该键接到目标 channel，再对齐 `linux,keycodes`。

**调试结论写法**：注明 DWS 文件名或路径、AI key 对应 GPIO 行截图/摘录（MODE、DIR、PULL、与 net 名）以及是否与 DTS 一致。

## 代码位置与参考

- **主参考目录**：`arch/arm64/boot/dts/mediatek/tp/`
- **完整 gpio-keys 定义示例**：`tran_mt6789_x6885_touch.dtsi`（`&odm` 下新建 `gpio_keys` + `aikey`）
- **基于板级已有节点的叠加示例**：`tran_mt6789_x6895_touch.dtsi`、`tran_mt6878_cm7_touch.dtsi`（`&gpio_keys { ... aikey { ... }; };`）
- **PMIC 按键扩展示例（少见）**：`tran_mt6789_cl6_touch.dtsi`（`&mt6366keys` 里给 `home` 增加 `linux,keycodes = <605>`）

适配新机型时：**优先复制同平台、同按键走线方式的 reference `*_touch.dtsi` 中的 AI key 片段**，再只改 GPIO 号与电平属性。

## 路径 A：`gpio-keys`（最常见）

### 适用

键线接到 **SoC GPIO**，由 `gpio-keys` 驱动扫描。

### 典型节点（与仓库一致）

新机可在 `&odm` 下定义（与 `tran_mt6789_x6885_touch.dtsi` 相同结构）：

```dts
&odm {
	gpio_keys: gpio_keys {
		compatible = "gpio-keys";
		status = "okay";
		aikey {
			label = "Ai_Key";
			linux,code = <605>;
			linux,input-type = <1>;
			gpios = <&pio 19 1>;
			wakeup-source;
			debounce-interval = <30>;
		};
	};
};
```

若 **主板基础 dtsi 已定义 `gpio_keys`**，则用 **节点覆盖** 只追加子键、并置 `status = "okay"`（见 `tran_mt6789_x6895_touch.dtsi`）：

```dts
&gpio_keys {
	status = "okay";
	aikey {
		label = "Ai_Key";
		linux,code = <605>;
		linux,input-type = <1>;
		gpios = <&pio 19 1>;
		wakeup-source;
		debounce-interval = <30>;
	};
};
```

### 必改项

| 属性 | 说明 |
|------|------|
| `gpios = <&pio N FLAGS>;` | `N` 为原理图/DWS 上的 **GPIO 编号**；`FLAGS` 为 **有效电平**（与硬件一致；仓库常见为第三位 `0`/`1` 表示 active high/low，须对照 PMIC GPIO 说明与原理图） |
| `linux,code = <605>;` | Transsion 侧 AI 键约定键值；**勿随意改** 除非与上层 Input 框架已对齐 |

### 可选但常用

- `linux,input-type = <1>`：`EV_KEY`
- `wakeup-source`：允许唤醒
- `debounce-interval = <30>;`：防抖（毫秒量级，可按硬件调整）

## 路径 B：`&mt6366keys`（PMIC 按键，少数机型）

### 适用

AI 功能复用 **PMIC 侧按键通道**（非独立 GPIO），如 `tran_mt6789_cl6_touch.dtsi`：

```dts
&mt6366keys {
	home {
		linux,keycodes = <605>;
		wakeup-source;
	};
};
```

此类需对照 **PMIC 文档与硬件**：`linux,keycodes` 与矩阵行列一致；**不要**与.gpio-keys 方案混用同一颗键的两套描述。

## 适配自检清单

1. **原理图**：AI 键接 GPIO 还是 PMIC KEY？GPIO 号与默认空闲电平、按下电平是否明确？
2. **DWS**：该脚 **GPIO 编号、模式（GPIO 非外设）、输入、上下拉** 是否与原理图及 DTS `gpios` 电平约定一致？（见上文「DWS 配置检查」）
3. **冲突**：该 GPIO 是否在 **pinctrl** 里被别的功能占用？若为纯输入键，一般无需额外 pinmux，但要确认未与 TP/SPI/I2C 等复用脚冲突。
4. **DTS 组织**：新机型 touch dtsi 是否在板级 DTS 中 `#include "mediatek/tp/..."`？
5. **与参考一致**：`linux,code`、节点命名（`aikey` / `Ai_Key`）与同系列已量产机是否一致，避免上层识别失败。
6. **验证**：
   - 开机 `dmesg | grep -i gpio-keys` 或 `input` 是否注册；
   - `getevent -l` 短按/长按是否出现 **605**（或映射后的 code）；
   - 休眠唤醒：有 `wakeup-source` 时能否唤醒。

## 与 TP 驱动的关系

AI key **不依赖** Touch IC vendor 驱动；放在 `mediatek/tp/` 下仅为 **项目文件组织习惯**。若问题仅为「按键无事件」，**不必改** `focaltech`/`goodix` 等 TP 代码；优先核对 **DWS → DTS 的 GPIO 与模式、电平**，再查 **pinctrl 冲突**。

## 输出模板（给评审 / 备注）

```markdown
## AI Key 适配结论
- 机型 / touch dtsi 路径：
- 方案：gpio-keys | mt6366keys
- DWS：文件/路径、AI key 脚 MODE/DIR/PULL、GPIO 号与 DTS 是否一致
- GPIO：`<&pio X FLAGS>` 或 PMIC 配置摘要
- linux code：605（是否与其它项目一致）
- 验证：getevent / dmesg 要点
```

---

改动原则：**只增加或修改 AI key 相关 DTS 片段**，不扩散改动无关 TP 供应商属性。
