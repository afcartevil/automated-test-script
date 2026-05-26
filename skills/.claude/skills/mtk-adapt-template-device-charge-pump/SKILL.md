---
name: mtk-adapt-template-device-charge-pump
description: MTK 项目 charge pump 适配模板，覆盖 kernel dtsi 参数、构建与打包、dws/pinctrl 映射以及 bootloader 依赖。
funcType: "AI自动化适配"
category: "驱动"
---

# MTK 器件模板：Charge Pump

## 适用范围

当需要适配 charge pump 硬件时使用本模板。

Preloader 阶段主要目标：
- 按平台策略在 preloader 进行 charge pump reset。
- 防止 charge pump 异常状态传导为 DpDm 异常。

典型耦合点：
- Charger and dvchg related DTSI nodes
- Kernel build switches and module packaging
- DWS and pinctrl for control and interrupt lines
- LK/preloader dependency alignment
- Preloader project DWS pin config (`codegen.dws`)

## 必填输入

- 器件型号（如 `hl7139a` / `hl7139` / `sc8548`）：
- charge pump 角色（`primary_dvchg` / `secondary_dvchg` / 双路）：
- 项目名（短名，如 `cm5`）：
- I2C 控制器与从地址（如 `&i2c12 + 0x5f`）：
- IRQ GPIO（`<&pio X flags>`）与是否存在 EN GPIO：
- 关联快充算法（PE5/PD/WLS）与项目功率档位：
- kernel DWS 路径（可选；若不提供则自动推导）：
- 目标项目路径（kernel、lk、preloader）：

## 全局基础参数解析（优先执行）

`project_full` 与 `mtk_platform_lower` 是跨阶段复用参数（kernel dtsi / kernel dws / bootloader 路径都会用到），应先解析再做后续适配。

### 0.1) `project_full` 解析规则

1) 输入项目短名（如 `cm5`）  
2) 在 `vendor/transsion/projects` 下匹配目录：  
- 优先匹配 `<project_short>_*`（如 `cm5_h8918`）  
- 命中目录全名即 `project_full`
3) 若命中多个目录：先要求用户指定完整项目名，再继续。

### 0.2) `mtk_platform_lower` 解析规则

1) 读取 `vendor/transsion/projects/<project_full>/ProjectConfig.mk`  
2) 解析 `MTK_PLATFORM = MTxxxx`  
3) 转为小写得到 `mtk_platform_lower`（例：`MT6878 -> mt6878`）

### 0.3) 全局输出（后续统一复用）

- `project_full = <project_full>`
- `mtk_platform_lower = <mtk_platform_lower>`
- `kernel_dws_path = vendor/mediatek/proprietary/tools/dct/dws/<mtk_platform_lower>/<project_full>.dws`

## 适配骨架

### 1) Kernel DTSI（可固化）

#### 1.1 识别到的 charge pump IC（6.12 + 6.1）

- `hl7139a`（主流，文件名常见 `tc_hl7139a.dtsi`）
- `hl7139`（少量项目，文件名常见 `tc_hl7139.dtsi`）
- `sc8548`（文件名常见 `sc8548.dtsi`）

> 结论：可以固化“按 IC 的节点模板 + 统一联动规则”，其中 I2C/GPIO/功率档参数保留用户输入。

#### 1.2 通用联动规则（固化）

- `tc_pe50.dtsi` 中 `&pe5 { tc_chgtype = <&tc_chgtype>; ... }` 仍作为算法主入口。
- charge pump 与 PE5 的关键联动不是 phandle，而是 `chg_name` 字符串：
  - 主路：`chg_name = "primary_dvchg";`
  - 副路：`chg_name = "secondary_dvchg";`
- 当项目为单路 charge pump：仅保留 `primary_dvchg` 节点。
- 当项目为双路 charge pump：增加 `secondary_dvchg`，并在 `tc_pe50.dtsi` 打开多路参数集（按项目实际）。

#### 1.2.1 常用参数基线（复扫后）

- `hl7139a` 常用基线：
  - `clock-frequency = <100000>`
  - `vbatovp = <4550000>` / `ibatocp = <8600000>`
  - `vbusovp = <11000000>` / `ibusocp = <4300000>` / `vinovp = <11000000>`
  - `wdt = <40000000>` / `ibat_rsense = <1>` / `i2c_vil_up = <1>` / `lt_wd_tmr = <3>`
  - `fsw_val = <6>`
- `sc8548` 常用基线：
  - `clock-frequency = <100000>`
  - `bat-ovp-threshold = <4525>` / `bat-ocp-threshold = <13000>`
  - `ac-ovp-threshold = <12000>` / `bus-ovp-threshold = <11000>` / `bus-ocp-threshold = <5000>`
  - `sense-resistor-mohm = <5>` / `fsw_val = <6>`
- 以上为“可直接起步”的通用值；若项目功率档或硬件电气不同，再按项目回填。

#### 1.3 HL7139A/HL7139 固化模板

```dts
&i2c<用户填写_I2C控制器> {
	#address-cells = <1>;
	#size-cells = <0>;
	clock-frequency = <100000>;

	hl7139a_master@<用户填写_I2C地址_十六进制> {
		compatible = "richtek,hl7139a";
		status = "okay";
		reg = <用户填写_I2C地址_十六进制>;
		rm_name = "hl7139a";
		rm_slave_addr = /bits/ 8 <用户填写_I2C地址_十六进制>;
		hl7139a,intr-gpios = <&pio 用户填写_IRQ_GPIO号 0x0>;

		standalone {
			chg_name = "primary_dvchg"; /* 用户填写：单路用primary，双路副路用secondary_dvchg */
			vbatovp = <4550000>;
			ibatocp = <8600000>;
			vbusovp = <11000000>;
			ibusocp = <4300000>;
			vinovp = <11000000>;
			wdt = <40000000>;
			ibat_rsense = <1>;
			i2c_vil_up = <1>;
			lt_wd_tmr = <3>;
			gpp_conf = <0>;
			fsw_val = <6>;
			protocol_i_masked;
			vbat_reg_dis;
			ibat_reg_dis;
			iin_reg_dis;
			tdie_reg_dis;
			ibatocp_dis;
		};
	};
};
```

HL7139A/HL7139 需要用户输入的字段：
- `&i2cX`（I2C 控制器）
- `reg` / `rm_slave_addr`（I2C 地址，如 `0x5f`/`0x5e`）
- `hl7139a,intr-gpios`（IRQ GPIO）
- `chg_name`（主路或副路）
- 是否双路（是否再复制一组 `@5e/@5f` 或独立 slave 控制器）

#### 1.4 SC8548 固化模板

```dts
&i2c<用户填写_I2C控制器> {
	#address-cells = <1>;
	#size-cells = <0>;
	clock-frequency = <100000>;

	sc8548_master@<用户填写_I2C地址_十六进制> {
		compatible = "sc,sc8548-standalone";
		chg_name = "primary_dvchg"; /* 用户填写：单路用primary，双路副路用secondary_dvchg */
		reg = <用户填写_I2C地址_十六进制>;
		sc8548,intr-gpios = <&pio 用户填写_IRQ_GPIO号 0x0>;

		sc,sc8548,bat-ovp-threshold = <4525>;
		sc,sc8548,bat-ocp-threshold = <13000>;
		sc,sc8548,ac-ovp-threshold = <12000>;
		sc,sc8548,bus-ovp-threshold = <11000>;
		sc,sc8548,bus-ocp-threshold = <5000>;
		sc,sc8548,sense-resistor-mohm = <5>;

		/* 二选一，按分支驱动属性名保留（用户确认） */
		fsw_val = <6>;
		/* sc,sc8548,switching_frequency = <6>; */

		/* 某些分支有 set_vil（用户确认） */
		/* set_vil; */

		status = "okay";
	};
};
```

SC8548 需要用户输入的字段：
- `&i2cX` 与 `reg`
- `sc8548,intr-gpios`（部分旧文件写成 `intr-gpio`，按驱动读法对齐）
- `chg_name`（主/副路）
- `bus-ovp-threshold`、`bat-ocp-threshold` 等阈值是否沿用机型默认
- 频率字段采用 `fsw_val` 还是 `switching_frequency`

#### 1.5 `tc_pe50.dtsi` 联动检查（固化）

至少检查以下项（值可按项目调优）：
- `support_ta`（常见 `"tfcp_adapter","pd_adapter"`，部分机型含 `"wireless_adapter"`）
- `run_cp_cur` / `run_cp_recovery_gap`
- `run_wls_cp_cur` / `run_wls_cp_recovery_gap`（若支持无线）
- 多路/多电池项目的扩展参数组是否与 `primary/secondary_dvchg` 一致

建议：
- 先固化结构和字段名，再由项目功率目标回填电流/温度曲线表。

#### 1.6 Kernel DWS 适配（新增，必做）

kernel 阶段同样需要 DWS 适配，和 preloader `codegen.dws` 不是同一个文件。

已确认的 kernel DWS 示例路径：
- `vendor/mediatek/proprietary/tools/dct/dws/mt6878/x6876_h786.dws`

Kernel DWS 路径自动解析规则（固化）：

1) 复用“全局基础参数解析（优先执行）”得到：
- `project_full`
- `mtk_platform_lower`

2) 拼接 kernel DWS 目标路径：
- `vendor/mediatek/proprietary/tools/dct/dws/<mtk_platform_lower>/<project_full>.dws`

3) 如果拼接路径不存在：
- 回报“自动推导失败”，并要求用户提供最终 dws 路径或项目全名。

Kernel DWS 在 charge pump 适配中的目标：
- 对齐 CP 相关 GPIO 的 pinmux/方向/上下拉/默认电平。
- 覆盖至少以下信号：I2C SCL/SDA、CP IRQ、CP EN（若硬件有）。
- 保证与 kernel dtsi 中使用的 GPIO 号一致（避免 dtsi 与 dws 脱节）。

#### 1.6.1 `protocol_ta.dtsi` 共用 I2C 与 DWS `varName0`（Tran）

若项目存在 **`protocol_ta.dtsi`**（`&i2cN` 下 `tfcp_ta`），该总线常与 **HL7139A / charge pump** 等共用。**SCL/SDA 对应的 GPIO 编号**在板级 dtsi 中可能不显式写出，须在 **芯片平台基 DTS**（如 `arch/arm64/boot/dts/mediatek/mt6897.dts`）中查找 **`i2cN`** 节点的 **`scl-gpio-id`**、**`sda-gpio-id`**（编号与 DWS `<gpioM>` 一致）。

在 **kernel DWS** 与 **preloader `codegen.dws`** 中，对上述两只 I2C 脚必须补充 **`<varName0>`**：

- SCL 脚：`TRAN_CHGPUMP_SCL_PIN`
- SDA 脚：`TRAN_CHGPUMP_SDA_PIN`

（迁移类任务同步见 `tran-projects-config-migrate-dtsi-dws` 中同条规则。）

Kernel DWS 输出约束（GPIO 号阶段）：
- 先按用户给定 GPIO 号落位，不臆造未确认的电气参数。
- 对未确认项显式标记 TODO（驱动/硬件再补值）。
- 最终交付时同时给出“dtsi GPIO 字段 <-> kernel dws 引脚项”的一一映射表。

### 2) Kernel Build and Packaging
- 增加 Kconfig 与 Makefile 使能
- 增加 ko csv 打包项

### 3) DWS and Pinctrl
- 配置总线与控制引脚
- 配置中断与使能引脚状态
- 区分 kernel DWS 与 preloader DWS 两套文件分别适配

### 4) Bootloader (LK/Preloader)
- 对齐所需构建宏
- 按需对齐早期引脚与电源行为（含 preloader 项目 DWS）
- 保证 preloader 的 charge pump reset 路径存在且可执行

## Preloader 适配（Charge Pump，已固化）

Preloader 目的提醒（charge pump）：
- 核心目的是早期开机阶段处理 charge pump reset。
- 用于避免残留/异常状态引发 DpDm 异常。

Preloader DWS 提醒：
- preloader 阶段同样需要 DWS 适配。
- DWS 文件是项目私有文件，例如：
  - `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/cm5_h8918/dct/dct/codegen.dws`
- 主要用于以下引脚功能配置：
  - I2C pins（含 **`protocol_ta` 所用总线**：在平台基 dts 查 `scl-gpio-id`/`sda-gpio-id` 后，在 `codegen.dws` 为对应 `<gpio>` 写 **`varName0`**：`TRAN_CHGPUMP_SCL_PIN` / `TRAN_CHGPUMP_SDA_PIN`，与 kernel DWS 一致）
  - enable pin
  - irq pin
- 当前策略：先按你提供的 GPIO 号做占位。
- pinmux/电气值后续补充。

### A) 驱动与宏映射

先解析：
- `vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/common/power/makefile`

Charge pump 相关宏到源文件映射：
- `HL7138_CHG_PUMP_SUPPORT` -> `hl7138.c`
- `SC8548_CHG_PUMP_SUPPORT` -> `pl_sc8548_charger.c`
- `SC8548D_CHG_PUMP_SUPPORT` -> `pl_sc8548d_charger.c`
- `SC760X_CHG_CURLMT_SUPPORT` -> `sc760x.c`
- `HL7139A_CHG_PUMP_SUPPORT` -> `hl7139a.c`

项目 mk 动作（preloader custom project mk）：
- 打开目标宏：`<CHG_PUMP_MACRO>=yes`
- 在 export 行导出宏

还需检查以下编译宏导入链路：
- `vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/common/power/feature.mak`
- 对每个已开启宏，确认：
  - `C_OPTION += -D<CHG_PUMP_MACRO>`
  - `export <CHG_PUMP_MACRO>`

### B) I2C ID 配置规则

#### 1) 共用 charge pump I2C 宏

以下驱动使用共用宏：
- `hl7138.c`
- `pl_sc8548_charger.c`
- `pl_sc8548d_charger.c`
- `hl7139a.c`

规则：
- Set `TRAN_CHG_PUMP_MASTER_I2C_ID=<bus_id>` in project mk
- Export `TRAN_CHG_PUMP_MASTER_I2C_ID`
- Confirm `feature.mak` has:
  - `C_OPTION += -DTRAN_CHG_PUMP_MASTER_I2C_ID="<value>"`
  - `export TRAN_CHG_PUMP_MASTER_I2C_ID`

原因：
- 这些驱动在代码中读取 `TRAN_CHG_PUMP_MASTER_I2C_ID`。
- 若未配置，部分驱动会回退到无效/哨兵 ID，导致初始化失败。

#### 2) SC760x 专用 I2C 宏

驱动：
- `sc760x.c`

规则：
- Set `TRAN_CHG_CURLMT_MASTER_I2C_ID=<bus_id>` in project mk
- Export `TRAN_CHG_CURLMT_MASTER_I2C_ID`
- Confirm `feature.mak` has:
  - `C_OPTION += -DTRAN_CHG_CURLMT_MASTER_I2C_ID="<value>"`
  - `export TRAN_CHG_CURLMT_MASTER_I2C_ID`

### C) Preloader 检查清单

- Macro enabled in preloader custom mk
- I2C ID macro set and exported in project mk
- Macro and I2C define exported through `feature.mak` (`C_OPTION += -D...`)
- Source file included via `power/makefile` macro path
- Driver `.c` consumes the same macro names (`#ifdef` path matches)
- Preloader build succeeds
- Early charge pump init/probe log is present

### D) Preloader 四层检查链（必做）

始终做端到端四层检查：

1) 项目 custom mk：
- enable macros
- set I2C IDs
- export macros

2) `feature.mak`：
- macro -> `-D` define
- I2C macro -> value define string
- export statements

3) `power/makefile`：
- macro -> `.c` file added into `MOD_SRC`

4) 驱动 `.c`：
- reads same macros in `#ifdef`
- fallback behavior understood

### E) Preloader DWS 适配（GPIO 号阶段）

当前输入方式：
- GPIO numbers for charge-pump-related signals (I2C SCL/SDA, EN, IRQ)

当前输出要求：
- 在 preloader `codegen.dws` 适配方案中记录 GPIO 号占位。
- 具体 pinmux 与电气参数保持 TODO。
- 映射规则未明确前，不臆造最终 DWS 值。

## LK 适配模板（当前状态）

### A) 规则文件检查

解析：
- `vendor/mediatek/proprietary/bootable/bootloader/lk2/platform/mediatek/common/charger/rules.mk`

当前对 charge pump 的结论：
- 该 `rules.mk` 中未看到专门的 charge-pump IC 宏到源文件映射。
- 该 `rules.mk` 中未导入专门的 charge-pump I2C 宏（`TRAN_CHG_PUMP_MASTER_I2C_ID` / `TRAN_CHG_CURLMT_MASTER_I2C_ID`）。

### B) LK 与 Preloader 器件差异（Charge Pump 维度）

preloader 已覆盖的 charge pump IC（已映射）：
- `HL7138`
- `SC8548`
- `SC8548D`
- `SC760X`
- `HL7139A`

LK 新增（相对 preloader 列表）：
- None found in current `lk2/.../charger/rules.mk`.

LK 缺失（相对 preloader 列表）：
- All above charge pump ICs are not explicitly mapped in current LK `rules.mk`.

### C) 交付规则

- 在 LK 适配要求中保留“charge pump reset”目标。
- 若项目要求 LK 显式映射 charge-pump IC，应先标记缺口并确认 LK 映射策略（新增宏或复用路径），再输出最终适配方案。

## 输出模板

- 需修改文件：
- 参数默认值与理由：
- 兼容性与依赖说明：
- 验证清单：
  - 编译通过
  - probe 成功
  - 观察到预期的 cp 状态变化

## 边界

- 仅做配置适配。
- 运行期算法调试仍由分析类技能处理。


