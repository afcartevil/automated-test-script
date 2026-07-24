---
name: mtk-adapt-template-device-pd-ic
description: MTK 项目 PD IC 适配模板，覆盖 kernel dtsi、TCPC/PD 构建开关、ko 打包、dws/pinctrl 以及 bootloader 联动点。
---

# MTK 器件模板：PD IC

## 三柱入口契约（柱 1）

本 skill 是 **`mtk-adapt-pillar1-router`** 柱 1 的下游模板。进入本 skill 前，应经 **`mtk-adapt-template-router`** 调度，且已有 `Adaptation Input Packet` 的 `Pillar 1 Device Inputs`；若来自老分支升级，该输入由 `mtk-adapt-upgrade-branch-orchestrator` / Inventory 生成。

### 输入

- `pd_ic`：器件型号、TCPC/PD 角色、PDO/PD 策略
- `bus_irq_gpio_power`：I2C、地址、IRQ、CC/控制脚、供电
- `Evidence`：`project_config`、`kernel_dws`、`preloader_codegen_dws`、`lk2_project_mk`、`charge_overlay`
- 老树升级时：老侧 TCPC/PD 节点、DWS、ProjectConfig/LK/PL 宏证据

### 输出

按 `Pillar Handoff Output` 输出：
- `pillar: 1`
- `downstream_skill: mtk-adapt-template-device-pd-ic`
- `Changes To Apply` 中列 TCPC/PD dtsi、DWS、构建开关、ko 打包、LK/PL 联动项
- `source` 标注原理图/老树证据/平台基准
- `review_tag` 标注需确认的 IRQ、CC、PDO、DRP/默认角色、DP AltMode 项

## 适用范围

当需要适配 PD IC 或 Type-C 控制器 IC 时使用本模板。

典型耦合点：
- TCPC/PD 相关 DTSI 条目
- 内核构建开关与打包
- CC/IRQ/I2C 相关 DWS 与 pinctrl
- LK 与 preloader 的同步配置

## 必填输入

- 器件型号（如 `rt1711h` / `rt1715` / `rt1718s` / `upm7610` / `aw35615` / `mt6375_typec` / `mt6370-tcpc`）：
- 项目名（短名，如 `cm5`）：
- TCPC/PD 角色（DRP/SRC/SNK，默认角色）：
- 总线与地址（I2C 控制器、7bit 地址）：
- IRQ GPIO 与触发类型（含 GPIO 编号）：
- PDO/PD 策略输入（source/sink pdo、charging-policy）：
- DP AltMode 输入（是否支持、pin assignment）：
- 目标项目路径（kernel、lk、preloader）：

## 全局基础参数解析（优先执行）

`project_full` 与 `mtk_platform_lower` 是跨文件复用参数（kernel dtsi / kernel dws / 其它项目路径），应先解析。

### 0.1) `project_full` 解析规则

1) 输入项目短名（如 `cm5`）  
2) 在 `vendor/transsion/projects` 下匹配 `<project_short>_*`  
3) 命中目录全名作为 `project_full`（如 `cm5_h8918`）  
4) 若命中多个目录，先要求用户指定完整项目名

### 0.2) `mtk_platform_lower` 解析规则

1) 读取 `vendor/transsion/projects/<project_full>/ProjectConfig.mk`  
2) 解析 `MTK_PLATFORM = MTxxxx`  
3) 转为小写得到 `mtk_platform_lower`（如 `MT6789 -> mt6789`）

### 0.3) 全局输出

- `project_full = <project_full>`
- `mtk_platform_lower = <mtk_platform_lower>`
- `kernel_dws_path = vendor/mediatek/proprietary/tools/dct/dws/<mtk_platform_lower>/<project_full>.dws`

## 适配骨架

### 1) Kernel DTSI（按 IC 固化）

#### 1.1 已识别 PD IC / TCPC 器件清单（6.12 + 6.1）

- `richtek,rt1711h`
- `richtek,rt1715`（RT 系列变体）
- `richtek,rt1718s`
- `unisemipower,upm7610`
- `awinic,aw35615`
- `mt6375_typec`（项目级 Type-C/PD 配置节点）
- `mediatek,mt6370-tcpc`（位于 `mt6370` 复合节点）

#### 1.1.1 常用参数基线（复扫后）

- RT 系（`rt1711h/rt1715`）  
  - 常用：`role-def = <5>`、`vconn-supply = <1>`、`source-pdo-size = <2>`、`sink-pdo-size = <1>`
  - `rp-level` 在基线间有差异：6.12 多为 `<2>`，6.1/部分 `rt1718s` 为 `<0>`
- UPM7610  
  - 高一致：`role-def = <5>`、`rp-level = <0>`、`vconn-supply = <1>`
  - 高一致：`source-pdo-size = <2>`、`sink-pdo-size = <1>`、`charging-policy = <0x31>`（或 `charging_policy` 写法）
- AW35615  
  - 高一致：`snk/src_pdo_size = <2>`
  - `snk_pdo_vol/snk_pdo_cur` 在项目间有两组常用值（见模板注释）
- MT6375 TypeC  
  - 6.12 常用：`charging-policy = <0x21>`、`sink-pdo-size = <2>`
  - 6.1 常用：`charging-policy = <2>`、`sink-pdo-size = <3>`

#### 1.2 RT 系（`rt1711h` / `rt1715` / `rt1718s`）模板

```dts
&i2c<用户填写_I2C总线号> {
	rt1711_typec: rt1711h@<用户填写_I2C地址_十六进制> {
		compatible = "richtek,rt1711h"; /* 或 richtek,rt1715 / richtek,rt1718s */
		reg = <用户填写_I2C地址_十六进制>;
		status = "okay";

		rt-tcpc,name = "type_c_port0";      /* 用户确认端口名 */
		rt-tcpc,role-def = <5>;             /* 常用：5 (Try.SNK) */
		rt-tcpc,rp-level = <2>;             /* 6.12常用:2；6.1/rt1718s常见:0 */
		rt-tcpc,vconn-supply = <1>;         /* 用户填写：Vconn 供电策略 */

		rt1711pd,intr-gpio = <&pio 用户填写_IRQ_GPIO号 0x0>;
		rt1711pd,intr-gpio-num = <用户填写_IRQ_GPIO号>;

		pd-data {
			pd,charging-policy = <0x31>;      /* 用户填写：PD 策略 */
			pd,source-pdo-size = <2>;         /* 常用：2 */
			pd,source-pdo-data = <0x00019032 0x000190c8>;/* 常用：5V500mA + 5V2A */
			pd,sink-pdo-size = <1>;           /* 用户填写：Sink PDO 数量 */
			pd,sink-pdo-data = <0x000190c8>;  /* 用户填写：Sink PDO 表 */
		};
	};
};
```

RT 系必填项：
- I2C 总线号、I2C 地址
- IRQ GPIO、IRQ 触发类型
- `role-def` / `rp-level` / `vconn-supply`
- `pd,source/sink pdo` 与 `charging-policy`
- 是否启用 DP AltMode（`displayport` 子节点）

#### 1.3 UPM7610 模板

```dts
&i2c<用户填写_I2C总线号> {
	upm7610@<用户填写_I2C地址_十六进制> {
		compatible = "unisemipower,upm7610";
		reg = <用户填写_I2C地址_十六进制>;
		status = "okay";

		up-tcpc,name = "type_c_port0";      /* 用户确认端口名 */
		up-tcpc,role-def = <5>;             /* 用户填写：默认角色策略 */
		up-tcpc,rp-level = <0>;             /* 用户填写：Rp 电流档位 */
		up-tcpc,vconn-supply = <1>;         /* 用户填写：Vconn 供电策略 */

		upm7610pd,intr-gpio = <&pio 用户填写_IRQ_GPIO号 0x0>;
		upm7610pd,intr-gpio-num = <用户填写_IRQ_GPIO号>;

		pd-data {
			pd,charging-policy = <0x31>;             /* 用户填写：PD 策略 */
			pd,source-pdo-size = <2>;                /* 用户填写：Source PDO 数量 */
			pd,source-pdo-data = <0x00019032 0x000190c8>; /* 用户填写：Source PDO 表 */
			pd,sink-pdo-size = <1>;                  /* 用户填写：Sink PDO 数量 */
			pd,sink-pdo-data = <0x000190c8>;         /* 用户填写：Sink PDO 表 */
		};
	};
};
```

UPM7610 必填项与 RT 系同类，额外确认：
- 驱动键名前缀是 `up-tcpc` / `upm7610pd`
- `notifier_supply_num` 等厂商扩展项是否需要保留

#### 1.4 AW35615 模板

```dts
&i2c<用户填写_I2C总线号> {
	aw35615@<用户填写_I2C地址_十六进制> {
		compatible = "awinic,aw35615";
		reg = <用户填写_I2C地址_十六进制>;
		aw35615,port_id = <0>;                    /* 用户填写：端口号 */
		awinic,int_n = <&pio 用户填写_IRQ_GPIO号 0>;
		status = "okay";

		aw35615,snk_pdo_size = <2>;               /* 常用：2 */
		aw35615,snk_pdo_vol = <5000 9000>;        /* 常用组合A(6.12)：<5000 9000>；组合B(6.1)：<5000 5000> */
		aw35615,snk_pdo_cur = <2000 2000>;        /* 常用组合A(6.12)：<2000 2000>；组合B(6.1)：<1000 2000> */
		aw35615,src_pdo_size = <2>;               /* 用户填写：Source PDO 数量 */
		aw35615,src_pdo_vol = <5000 5000>;        /* 用户填写：Source PDO 电压 */
		aw35615,src_pdo_cur = <500 2000>;         /* 用户填写：Source PDO 电流 */
	};
};
```

AW35615 必填项：
- I2C bus/address
- `awinic,int_n`
- `snk/src pdo` 数量与电压电流表
- 端口切换与阈值配置（如 `snk_tog_time/src_tog_time`）

#### 1.5 MTK 内建 TCPC（`mt6375_typec` / `mt6370-tcpc`）模板

```dts
&mt6375_typec {
	pd-data {
		pd,charging-policy = <0x21>;             /* 6.12常用:0x21；6.1常用:2 */
		pd,source-pdo-size = <2>;                /* 用户填写：Source PDO 数量 */
		pd,source-pdo-data = <0x00019032 0x000190c8>; /* 用户填写：Source PDO 表 */
		pd,sink-pdo-size = <2>;                  /* 6.12常用:2；6.1常用:3 */
		pd,sink-pdo-data = <0x000190c8 0x000190c8>;   /* 6.1常见可扩展为3个PDO(含9V/PPS) */
	};
	dpm-caps {
		local-dr-power;
		local-dr-data;
		local-usb-comm;
		local-no-suspend;
	};
};
```

内建 TCPC 必填项：
- `pd-data` 全量能力描述
- `dpm-caps` 与项目角色策略
- 是否启用 `displayport` 及 pin assignment
- 与 charger 节点绑定关系（如 `charger = <&...>`）

#### 1.6 框架联动检查（固化）

在项目 `tc_charger.dtsi` / `protocol_ta.dtsi` 中至少确认：
- `tc_pd` 或 `pd_adapter` 节点存在且启用
- `tc_tcpc` 适配层存在且启用（事件上报链路）
- `tc_chgtype` 与 charger/gauge/typec 依赖关系闭环
- 若项目存在 `tc_pdlc.dtsi`，确认其与 PD/Type-C 状态协同关系

### 2) Kernel Build and Packaging
- 更新 Kconfig 与 Makefile
- 若为模块形态，补充 ko csv 打包项

### 3) DWS and Pinctrl
- 配置 I2C 与 IRQ 引脚
- 配置 CC 或相关 GPIO 控制引脚
- 保证运行时 pin 状态与 DTSI 命名一致
- 使用 `kernel_dws_path` 自动解析结果定位文件

### 4) Bootloader (LK/Preloader)
- 按需增加构建宏
- 同步关键引脚与电源初始化设置

## 输出模板

- 需修改文件：
- 修改摘要（按 IC 分类）：
- 预期 attach/PD 行为：
- 验证清单：
  - 编译通过
  - tcpc probe 日志存在
  - attach 事件链路正常
  - 进入 PD 协商流程

## 边界

- 本模板阶段不改协议栈 `.c/.h`。
- 若 attach/协商异常原因未定位，先走分析类技能链路。


