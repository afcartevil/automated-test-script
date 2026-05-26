---
name: mtk-adapt-template-device-charger-ic
description: MTK 项目 charger IC 适配模板，覆盖 kernel dtsi、内核构建与打包、dws/pinctrl 以及 bootloader（lk/preloader）联动点。
funcType: "AI自动化适配"
category: "驱动"
---

# MTK 器件模板：Charger IC

## 适用范围

当需要适配 charger IC 器件时使用本模板。
在本项目语境下，charger IC 也称 switch IC（开关 IC）。

Preloader 阶段主要目标：
- 在 preloader 阶段完成 BC1.2 充电类型识别。
- 稳定识别 SDP，保证设备可按预期进入 meta 模式。

典型耦合点：
- Kernel DTSI 节点与属性
- 内核构建与模块打包
- DWS 与 pinctrl（I2C、IRQ、EN）
- Bootloader 配置（LK 与 preloader）
- preloader 项目 DWS 引脚配置（`codegen.dws`）

## 必填输入

- 器件型号：
- 总线类型与地址：
- IRQ 引脚与触发类型：
- Enable/Reset 引脚：
- 供电信息：
- 驱动模块名：
- 目标项目路径（kernel、lk、preloader）：
- `tc_charger_lk.dtsi` 目标路径（优先由用户明确指定）：
- Kernel DTSI 输入（用户提供）：
  - I2C 控制器号（如 `&i2c0` / `&i2c5`）
  - 设备地址（如 `0x6b`）
  - IRQ GPIO（gpio 号 + 触发类型）
  - EN/CE GPIO（如器件需要）
  - USB PHY 引用（`phys` / `phy-names` / `usb`）
  - OTG regulator 电压电流范围（如器件节点内需要）

## 适配骨架

### 1) Kernel DTSI
- 新增/修改 charger IC 节点
- 填写 compatible/reg/interrupts/gpios/supply 等属性
- 补充 include 与 status 开关

### 1.1) Kernel 联动规则（固化）

- 与充电框架联动时，不直接写 `switch_chg` 作为联动目标。
- 统一通过 `tc_chgtype` 节点对上层充电框架联动。
- 固化联动写法：
  - 在 `tc_charger.dtsi` 中：`tc_chgtype` 的 `charger = <&<ic_charger_node>>;`
  - 在 `&charger` / `&mtk_gauge` / `&extcon_usb` 等框架节点中，联动 `tc_chgtype`（不直接绑到具体 `switch_chg` 节点）。

### 1.2) Kernel DTSI 固化模板（按 IC）

以下模板仅固化结构与关键字段；I2C 通路号、GPIO 引脚、地址等都保留为用户输入。

#### 1.2.1) 常用参数基线（复扫后）

- `sc8950/sc6602` 常用基线：
  - `chg_name = "primary_chg"`
  - `phys = <&u2port0 PHY_TYPE_USB2>` + `phy-names = "usb2-phy"`
  - OTG 常用起步：`4850000~5400000 uV`，`500000~2000000 uA`（大电流机型可上调）
- `sgm41516s` 常用基线：
  - `clock-frequency = <400000>`
  - `phy` 仍按 `u2port0 + usb2-phy` 联动
- `rt9471` 常用基线：
  - 外层 `compatible = "richtek,swchg"`
  - 子节点 `chg_name = "primary_chg"` / `chg_alias_name = "rt9471_chg"`
  - 中断通常走 `interrupts-extended`
- `mt6375_typec` 常用基线：
  - `pd,vid = <0x29cf>` / `pd,pid = <0x6375>`
  - 其余 PDO 能力按项目功率档回填

#### A) `sc8950`

```dts
&<用户填写_I2C控制器> {
	#address-cells = <1>;
	#size-cells = <0>;
	sc8950_chg: sc-swchg@<用户填写_I2C地址_十六进制> {
		compatible = "southchip,sc8950";
		reg = <<用户填写_I2C地址_十六进制>>;
		status = "okay";
		sc8950,intr_gpio = <&pio <用户填写_IRQ_GPIO号> 0x0>;
		phys = <&u2port0 PHY_TYPE_USB2>;
		phy-names = "usb2-phy";
		usb = <&usb>;
		chg_name = "primary_chg";
		chg_alias_name = "sc8950_chg";
		otg_vbus: usb-otg-vbus {
			regulator-compatible = "usb-otg-vbus";
			regulator-name = "usb-otg-vbus";
			regulator-min-microvolt = <4850000>; /* 用户可改：常用下限 */
			regulator-max-microvolt = <5400000>; /* 用户可改：常用上限 */
			regulator-min-microamp = <500000>;   /* 用户可改：常用下限 */
			regulator-max-microamp = <2000000>;  /* 用户可改：常用上限 */
		};
	};
};
```

#### B) `sc6602`（可与 `sc8950` 兼容）

```dts
&<用户填写_I2C控制器> {
	#address-cells = <1>;
	#size-cells = <0>;
	sc6602_chg: sc-swchg@<用户填写_I2C地址_十六进制> {
		compatible = "southchip,sc6602", "southchip,sc8950";
		reg = <<用户填写_I2C地址_十六进制>>;
		status = "okay";
		sc6602,intr_gpio = <&pio <用户填写_IRQ_GPIO号> 0x0>;
		sc8950,intr_gpio = <&pio <用户填写_IRQ_GPIO号> 0x0>;
		chg_name = "primary_chg";
		chg_alias_name = "sc6602_chg";
	};
};
```

#### C) `sgm41516s`

```dts
&<用户填写_I2C控制器> {
	status = "okay";
	clock-frequency = <400000>;
	sgm41516s_chg: sgm41516s@<用户填写_I2C地址_十六进制> {
		compatible = "sgm,sgm41516s";
		reg = <<用户填写_I2C地址_十六进制>>;
		status = "okay";
		sgm,intr_gpio = <&pio <用户填写_IRQ_GPIO号> 0x0>;
		phys = <&u2port0 PHY_TYPE_USB2>;
		phy-names = "usb2-phy";
		usb = <&usb>;
		chg_alias_name = "sgm41516s";
	};
};
```

#### D) `rt9471`

```dts
&<用户填写_I2C控制器> {
	#address-cells = <1>;
	#size-cells = <0>;
	rt9471_chg: rt-swchg@<用户填写_I2C地址_十六进制> {
		compatible = "richtek,swchg";
		reg = <<用户填写_I2C地址_十六进制>>;
		status = "okay";
		interrupts-extended = <&pio <用户填写_IRQ_GPIO号> <用户填写_IRQ触发类型>>;
		phys = <&u2port0 PHY_TYPE_USB2>;
		phy-names = "usb2-phy";
		usb = <&ssusb>;
		rt9471 {
			chg_name = "primary_chg";
			chg_alias_name = "rt9471_chg";
			charger = <&rt9471_chg>;
			/* 其余 mivr/aicr/cv/ichg/ieoc 等参数按项目输入 */
		};
	};
};
```

#### E) `rt6160`（电源/boost 侧器件，按项目决定是否纳入主 charger 路径）

```dts
&<用户填写_I2C控制器> {
	rt6160@<用户填写_I2C地址_十六进制> {
		compatible = "richtek,rt6160";
		reg = <<用户填写_I2C地址_十六进制>>;
		regulator-name = "rt6160-buckboost";
		regulator-min-microvolt = <<用户填写_VOUT_uV>>;
		regulator-max-microvolt = <<用户填写_VOUT_uV>>;
		regulator-always-on;
	};
};
```

#### F) `mt6375`（Type-C/PD 侧）

```dts
&mt6375_typec {
	pd-data {
		pd,vid = <0x29cf>;
		pd,pid = <0x6375>;
		/* 用户填写：pdo/capability */
	};
};
```

### 1.3) `tc_chgtype` 统一联动模板（固化）

```dts
&odm {
	tc_chgtype: tc_chgtype {
		compatible = "tc_chgtype";
		charger = <&<用户填写_充电器节点标签>>;
		phys = <&u2port0 PHY_TYPE_USB2>;
		phy-names = "usb2-phy";
		usb = <&ssusb>;
		status = "okay";
	};
};

&charger {
	charger = <&tc_chgtype>;
};

&mtk_gauge {
	charger = <&tc_chgtype>;
};

&extcon_usb {
	charger = <&tc_chgtype>;
};
```

说明：
- `<用户填写_充电器节点标签>` 由具体 IC 节点标签替换（如 `sc8950_chg`、`rt9471_chg`、`sgm41516s_chg`）。
- I2C 通路号、GPIO、地址、中断类型全部由用户输入决定。

### 2) Kernel Build and Packaging
- 更新 Kconfig 与 Makefile 条目
- 更新 ko csv 打包条目

### 3) DWS and Pinctrl
- 配置 I2C 总线引脚
- 配置 IRQ 与 EN 引脚模式
- 对齐 DTSI 使用的 pinctrl state 命名

### 4) Bootloader (LK/Preloader)
- 打开必要构建宏
- 配置板级 dws 引脚（含 preloader 项目 DWS）
- 保证早期电源/引脚初始化与 kernel 对齐
- 保证 preloader 充电路径可执行 BC1.2，且 SDP 结果稳定用于 meta 进入

## Preloader 适配模板（必做）

Preloader 目的提醒（charger IC）：
- 适配目标不只是早期 probe。
- 核心是 preloader 阶段 BC1.2 检测，尤其是 SDP 稳定识别与 meta 进入。

Preloader DWS 提醒：
- preloader 阶段也需要 DWS 适配。
- DWS 文件是项目私有文件，例如：
  - `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/cm5_h8918/dct/dct/codegen.dws`
- 主要用于以下引脚功能配置：
  - I2C pins
  - enable pin
  - irq pin
- 当前策略：先按你提供的 GPIO 号做占位适配。
- 具体 pinmux/电气值后续补充。

### A) 驱动存在性检查

检查 charger IC 的 preloader 驱动是否存在于以下任一路径：
- `vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/common/power/`
- `vendor/vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/common/power/`

若驱动不存在，先停止并报告“当前分支缺少 preloader 支持”。

### B) 项目 Makefile 配置

修改项目 preloader mk，通常是：
- `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/<project>.mk`

必备配置模式：
- 打开 charger IC 宏：
  - `<CHARGER_IC_MACRO>=yes`
- 配置 charger IC I2C 总线号：
  - `<CHARGER_IC_I2C_ID_MACRO>=<bus_id>`
- export 相关宏：
  - `export ... <CHARGER_IC_MACRO> <CHARGER_IC_I2C_ID_MACRO> ...`

### B.1) Preloader Power Makefile 宏映射（先解析）

Before changing project mk, parse:
- `vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/common/power/makefile`

这个文件是事实来源，用于确认：
- 哪个宏会拉入哪个 charger/charge-pump 源文件
- 目标 IC 是否已经具备 preloader 支持

当前宏到源文件映射（来自该 makefile）：

| Macro | Source file |
| --- | --- |
| `MT6375_PMU` | `mt6375.c` |
| `MT6360_PMU` | `mt6360.c` |
| `MTK_5G_B_MT6360_MT6315` | `mt6360.c` |
| `MT6370_PMU` | `mt6370.c` |
| `RT9471_CHG` | `rt9471.c` |
| `SC8950_CHG` | `sc8950.c` |
| `UPM6926_CHG` | `upm6926_charger.c` |
| `HL7138_CHG_PUMP_SUPPORT` | `hl7138.c` |
| `SC8548_CHG_PUMP_SUPPORT` | `pl_sc8548_charger.c` |
| `SC8548D_CHG_PUMP_SUPPORT` | `pl_sc8548d_charger.c` |
| `MTK_BQ25601_SUPPORT` | `bq25601_pl.c` |
| `HL7139A_CHG_PUMP_SUPPORT` | `hl7139a.c` |
| `SC760X_CHG_CURLMT_SUPPORT` | `sc760x.c` |
| `SD76930_CHG` | `sd76930_pl.c` |
| `RT6160` | `rt6160.c` |
| `SGM41516S_CHG` | `sgm41516s_pl.c` |

同文件中的相关特性宏：
- `TRAN_PL_AUXADC_BAT_SUPPORT` -> adds `-DTRAN_PL_AUXADC_BAT_SUPPORT` to preloader CFLAGS

判定规则：
- 若目标 IC 宏在映射中存在：在项目 mk 中开启并 export。
- 若目标 IC 宏不存在：判定为 preloader 支持缺失，先做驱动/宏 bring-up。

### B.2) Preloader I2C ID 规则（已固化）

以下 IC 的 I2C-ID 规则已固化：

| Driver file | I2C source rule | Project-side action |
| --- | --- | --- |
| `sc8950.c` | `TRAN_SC8950_CHG_I2C_ID` if defined, else `I2C5` | Set `TRAN_SC8950_CHG_I2C_ID=<bus_id>` in project mk and export it |
| `upm6926_charger.c` | `TRAN_UPM6926_CHG_I2C_ID` if defined, else `I2C5` | Set `TRAN_UPM6926_CHG_I2C_ID=<bus_id>` and export it |
| `sgm41516s_pl.c` | `TRAN_SGM41516s_CHG_I2C_ID` if defined, else `I2C5` | Set `TRAN_SGM41516s_CHG_I2C_ID=<bus_id>` and export it |
| `bq25601_pl.c` | `TRAN_SGM41516_CHG_I2C_ID` if defined, else `I2C5` | Set `TRAN_SGM41516_CHG_I2C_ID=<bus_id>` and export it |
| `rt9471.c` | `I2C6` when `RT9471_I2C6_NUM` is defined, else `I2C5` | Choose by compile macro path, no `TRAN_*_I2C_ID` macro |
| `mt6360.c` | fixed `I2C5` | Usually no project I2C macro needed |
| `mt6370.c` | fixed `I2C5` | Usually no project I2C macro needed |
| `mt6375.c` | fixed `I2C5` (in `bank_to_i2c`) | Usually no project I2C macro needed |
| `rt6160.c` | fixed `I2C3` | Usually no project I2C macro needed |
| `sd76930_pl.c` | fixed `I2C6` (`SD76930_I2C_ID`) | Usually no project I2C macro needed |

暂未固化（当前有意排除）：
- `hl7138.c`
- `pl_sc8548_charger.c`
- `pl_sc8548d_charger.c`
- `sc760x.c`
- `hl7139a.c`

### B.3) Preloader 四层检查链（必做）

在 preloader 打开 charger IC 时，必须检查以下四层：

1) 项目 custom mk（项目本地配置）
- 文件模式：
  - `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/<project>.mk`
 - 动作：
  - Enable IC macro (`...=yes`)
  - Set optional I2C macro if the driver supports it
  - Add/export related macros

2) `feature.mak`（宏 -> 编译器 define）
- 文件：
  - `vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/common/power/feature.mak`
 - 动作：
  - Confirm IC macro is converted to `C_OPTION += -D<MACRO>` and exported
  - Confirm I2C macro is passed as `-D<MACRO>="<value>"` when required
- 本文件中已知 charger IC 相关宏块包括：
  - `MT6375_PMU`, `MT6370_PMU`, `MT6360_PMU`, `RT9471_CHG`
  - `SC8950_CHG`, `UPM6926_CHG`, `SGM41516S_CHG`, `MTK_BQ25601_SUPPORT`
- I2C define/export 宏块：
    - `TRAN_SC8950_CHG_I2C_ID`
    - `TRAN_UPM6926_CHG_I2C_ID`
    - `TRAN_SGM41516_CHG_I2C_ID`
    - `TRAN_SGM41516S_CHG_I2C_ID`

3) `power/makefile`（宏 -> 源文件纳入）
- 文件：
  - `vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/common/power/makefile`
 - 动作：
  - Confirm enabled macro really adds target `.c` into `MOD_SRC`

4) 驱动 `.c`（宏实际消费）
- 动作：
  - Confirm source uses the expected macro in `#ifdef` path
  - Confirm fallback behavior (default I2C or fixed I2C) matches project expectation

停止规则：
- 任意一层缺失或不一致，都必须先修正链路一致性，再做编译验证。

### C) CM5 sc8950 示例（参考）

From:
- `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/cm5_h8918/cm5_h8918.mk`

观察到的配置模式：
- `SC8950_CHG=yes`
- `TRAN_SC8950_CHG_I2C_ID=0`
- Both included in export line

可将其作为其他 charger IC 的宏连线参考。

### D) Preloader DWS 适配（GPIO 号阶段）

当前输入方式：
- GPIO numbers for charger-related signals (I2C SCL/SDA, EN, IRQ)

当前输出要求：
- 在 preloader `codegen.dws` 适配方案中记录 GPIO 号占位。
- 具体 pinmux 与电气参数保留为 TODO。
- 在映射规则未给出前，不臆造最终 DWS 值。

## LK 适配模板（必做）

### A) 规则文件与连线模型

先解析：
- `vendor/mediatek/proprietary/bootable/bootloader/lk2/platform/mediatek/common/charger/rules.mk`

LK 连线模型：
- 项目 mk 负责赋值（如 `lk2/project/<project>.mk`）
- `rules.mk` 消费变量并映射到：
  - `MODULE_SRCS += <driver>.c`
  - `GLOBAL_DEFINES += <MACRO>` or `GLOBAL_DEFINES += <I2C_MACRO>=<value>`

说明：
- LK 路径通常不需要 preloader 那套 `export ...` + `C_OPTION += -D...`。
- LK 生效路径主要是 `GLOBAL_DEFINES`。
- 对三方 charger IC（IC 名非 `mt` 前缀），LK 项目 mk 还必须打开：
  - `COMPATIBLE_SWITCHIC_SUPPORT = yes`
  - Reference pattern: `lk2/project/cm5_h8918.mk`
- 还需做代码存在性检查：
  - `vendor/mediatek/proprietary/bootable/bootloader/lk2/platform/mediatek/common/charger/mtk_charger.c`
  - 确认存在 `#if defined(COMPATIBLE_SWITCHIC_SUPPORT)` 分支。
  - 若缺失，判定该分支不具备此功能。

### A.1) LK 阶段适配目的（为何要开这些宏）

LK 侧 charger IC 适配目的：
- During LK boot, system checks battery voltage (VBAT).
- If VBAT is below boot threshold, LK enters pre-charge flow.
- In pre-charge flow, charger IC must:
  - confirm VBUS is present
  - execute charging control (AICR/ICHG/prechg/current limit path)

`mtk_charger.c` 主流程：
- `mtk_charger_start()` -> `check_low_battery()` -> `check_charging_status()` (single battery)
- low battery with charger present triggers pre-charge and charge regulation loop
- no charger in low battery path leads to power off

### B) LK Charger IC 宏映射（来自 `rules.mk`)

| LK macro | Driver source |
| --- | --- |
| `SC8950_CHARGER_SUPPORT` | `sc8950.c` |
| `UPM6926_CHARGER_SUPPORT` | `upm6926_charger.c` |
| `MTK_SGM41516S_SUPPORT` | `sgm41516s_lk.c` |
| `MTK_SGM41516D_SUPPORT` | `sgm41516d.c` |
| `MTK_RT9470D_SUPPORT` | `rt9470d.c` |
| `MTK_MT6379_2P_CHARGER_SUPPORT` | `mt6379_2p.c` |
| `MTK_MT6375_CHARGER_SUPPORT` | define-only in this file |

三方 charger IC 策略：
- “三方 charger IC”指 IC 名称不以 `mt` 开头。
- 除器件宏外，LK 项目 mk 还需开启 `COMPATIBLE_SWITCHIC_SUPPORT = yes`。
- 同时确认 `mtk_charger.c` 中存在该宏守护逻辑。

`COMPATIBLE_SWITCHIC_SUPPORT` 的影响（已在 `mtk_charger.c` 确认）：
- 会改变 LK 的 VBUS 取值路径：
  - with macro: `get_chr_volt()` uses `AUXADC_CHAN_VCDT` and resistor conversion (`r_charger_1`, `r_charger_2`)
  - without macro: `get_chr_volt()` uses `mtk_charger_get_vbus()`
- 因此该宏会直接影响低电/预充流程中的“VBUS 在位”判断。

### C) LK I2C-ID 宏映射（来自 `rules.mk`)

| LK I2C macro | Consumption |
| --- | --- |
| `TRAN_SC8950_CHARGER_I2C_ID` | passed to `sc8950.c` via `GLOBAL_DEFINES` |
| `TRAN_UPM6926_CHARGER_I2C_ID` | passed to `upm6926_charger.c` |
| `TRAN_SGM41516S_CHARGER_I2C_ID` | passed to `sgm41516s_lk.c` |
| `TRAN_SGM41516_CHARGER_I2C_ID` | passed to `sgm41516d.c` |

### D) LK 与 Preloader 器件差异（当前已知集）

共同覆盖（两侧都有）：
- `SC8950`, `UPM6926`, `SGM41516S family`, `MT6375 family`

LK 新增（相对当前 preloader 集合）：
- `SGM41516D` (`MTK_SGM41516D_SUPPORT`)
- `MT6379_2P` (`MTK_MT6379_2P_CHARGER_SUPPORT`)
- `RT9470D` (`MTK_RT9470D_SUPPORT`)

仅 preloader 存在（在当前 LK `rules.mk` 未映射）：
- `RT9471_CHG`
- `MT6360_PMU`
- `MT6370_PMU`
- `SD76930_CHG`
- `RT6160`
- `MTK_BQ25601_SUPPORT`

执行规则：
- 每个目标 charger IC 都要确认 preloader 与 LK 两侧映射均存在。
- 任一侧缺失时，先标记为跨 bootloader 覆盖缺口，再进入交付。
- 目标为三方 charger IC（非 `mt` 前缀）时，确认 LK 项目 mk 已开启 `COMPATIBLE_SWITCHIC_SUPPORT = yes`。
- 三方 charger IC 还需确认 `mtk_charger.c` 存在 `COMPATIBLE_SWITCHIC_SUPPORT` 分支；若缺失则停止并报告“分支能力缺失”。

### E) LK 充电调控参数检查清单（`mediatek,lk_charger`）

除宏开关外，LK 充电调控还依赖以下 DT 参数（在此解析）：
- `lk2/platform/mediatek/common/charger/mtk_charger.c` (`init_cust_data_from_dt`)

`tc_charger_lk.dtsi` 路径规则（固化）：
- 优先策略：由用户明确给出生成目标路径。
- 未给出时按内核版本使用默认相对路径模板：
  - 6.1：`vendor/kernel/kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/<project>/tc_charger_lk.dtsi`
  - 6.12：`kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/charge/<project>/tc_charger_lk.dtsi`
  - 6.6：`kernel/kernel_device_modules-6.6/arch/arm64/boot/dts/mediatek/charge/<project>/tc_charger_lk.dtsi`
- 其中 `<project>` 由项目名替换（例如 `x6873`、`cm5_h8918`）。
- 若默认路径不存在，执行路径回退：
  - 先尝试在路径前增加 `vendor/`
  - 若当前是 `vendor/...`，再尝试去掉 `vendor/`
- 说明：`vendor/` 是否存在与本地拉代码方式有关。

基线固定参数（当前先固定，不随项目改动）：
- `compatible = "mediatek,lk_charger"`
- 动画/电源路径开关：
  - `enable-anime`
  - `power-path-support`
- `max-charger-voltage = <6500000>`
- `low-bat-temp-boot-vbat = <3600000>`
- `fast-charge-voltage = <2500000>`
- `cur-threshold = <500000>`
- `temp-t0-current = <1500000>`
- `temp-neg-t0-current = <500000>`
- `temp-t4-threshold = <55>`
- `temp-t3-threshold = <45>`
- `temp-t2-threshold = <15>`
- `temp-t1-threshold = <10>`
- `temp-t0-threshold = <0>`
- `temp-neg-t0-threshold = <(-20)>`

固定 charging current 参数组：
- `usb-charger-current = <500000>`
- `ac-charger-current = <2000000>`
- `ac-charger-input-current = <2000000>`
- `non-std-ac-charger-current = <1200000>`
- `charging-host-charger-current = <1500000>`
- `ta-ac-charger-current = <3000000>`
- `pd-charger-current = <500000>`

固定策略：
- 以上参数作为 LK dtsi 首批固定基线，默认不改。
- 后续参数按用户逐项下发再配置。
- 键名风格统一固定为连字符（`-`），不再使用下划线（`_`）风格。

建议检查/配置的参数组：

1) 启动与低电阈值
- `boot-battery-voltage`
- `boot-chg-battery-voltage`
- `low-power-charger-vbat`
- `low-bat-temp-boot-vbat`
- `fast-charge-voltage`

2) VBUS 有效性与安全窗口
- `min-charger-voltage`
- `max-charger-voltage`

3) 按充电类型区分的电流上限
- `usb-charger-current`
- `ac-charger-current`
- `ac-charger-input-current`
- `non-std-ac-charger-current`
- `charging-host-charger-current`
- `ta-ac-charger-current`
- `pd-charger-current`

4) 预充行为调优
- `prechg-cur`
- `pre-charge-timeout`
- `pre-charging-idle-time`
- `wait-adapter-stabilization`

`prechg-cur` 规则（固化）：
- `prechg-cur` 目标值按 `0.05C` 计算。
- 这里的 `C` 定义为：电池最小容量（minimum battery capacity）。
- 电池参数变更时，需要联动重算 `prechg-cur`，避免 charger 与 battery 配置不一致。

5) 三方 switch IC 的 VBUS 分压参数（`COMPATIBLE_SWITCHIC_SUPPORT=yes` 时关键）
- `r-charger-1`
- `r-charger-2`

6) 可选能力调优
- `enable-try-ta-cap`
- `boot-voltage-level`
- `ta-capability-level`
- temperature/current derating related thresholds (`temp-*`, `cur-threshold`)

实践规则：
- 若项目开启了三方 charger IC 路径，但分压/电流/超时等仍沿用默认且未评审，应标记为“LK 充电策略未完成适配”。

## 输出模板

- 需修改文件：
- 每个文件：改动项 -> 原因 -> 预期效果
- 风险与回退方案：
- 验证清单：
  - 编译通过
  - preloader 宏与 export 生效
  - preloader 充电路径达到预期初始化阶段
  - 模块已打包
  - probe 日志存在
  - 充电路径可见

## 边界

- 未经明确要求，不改 `.c/.h`。
- 若 charger 行为问题尚未定位，先走分析类技能。


