---
name: mtk-adapt-template-device-gauge
description: MTK 项目 gauge 器件配置模板，覆盖 kernel dtsi、构建集成、可选模块打包、按需 dws/pinctrl；LK 中与 gauge 类型相关的 Tran 宏（TRAN_SINGLE_GAUGE / TRAN_DUAL_BATTERY / TRAN_LOW_BATTERY_SUPPORT）语义与核对纪律见 § Bootloader。
---

# MTK 器件模板：Gauge

## 三柱入口契约（柱 1）

本 skill 是 **`mtk-adapt-pillar1-router`** 柱 1 的下游模板。进入本 skill 前，应经 **`mtk-adapt-template-router`** 调度，且已有 `Adaptation Input Packet` 的 `Pillar 1 Device Inputs`；若来自老分支升级，该输入由 `mtk-adapt-upgrade-branch-orchestrator` / Inventory 生成。

### 输入

- `gauge`：平台 gauge / 三方 gauge 类型、器件型号、单双电池信息
- `bus_irq_gpio_power`：I2C/通信接口、IRQ/检测脚、供电或电池检测相关脚位
- `Evidence`：`project_config`、`kernel_dws`、`preloader_codegen_dws`、`lk2_project_mk`、`charge_overlay`
- 老树升级时：老侧 battery/gauge dtsi、LK/PL 宏、DWS 证据

### 输出

按 `Pillar Handoff Output` 输出：
- `pillar: 1`
- `downstream_skill: mtk-adapt-template-device-gauge`
- `Changes To Apply` 中列 gauge/battery_prop dtsi、DWS、构建/打包、LK/PL 宏项
- `source` 标注电池规格/平台基准/老树证据
- `review_tag` 标注需确认的单双电、低电支持、gauge 类型、电池表来源项

## 通用规则

- 规则1（内核路径拼接）：
  - 涉及内核 `dtsi`、`.c`、`.h` 的修改或规则分析时，统一使用 `kernel_device_modules-*` 作为中间目录进行路径拼接。
- 规则2（版本映射）：
  - `A16` 是安卓 `W`，对应 `6.12` 内核。
  - `A15` 是安卓 `V`，对应 `6.6` 内核。
  - `A14` 是安卓 `U`，对应 `6.1` 内核。
  - 路径示例：`kernel/kernel_device_modules-6.12/...`、`kernel/kernel_device_modules-6.6/...`、`vendor/kernel/kernel_device_modules-6.1/...`。
- 规则3（平台基准 dtsi）：
  - `kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/bat_setting` 视为平台基准 dtsi 目录（芯片厂家按芯片给出的模板）。
  - 对于需要参考值的配置项，优先从平台基准 dtsi（同名 `*_battery_prop.dtsi` / 相关表）读取后再同步到项目 dtsi。
  - 若项目配置与平台基准不一致，需在适配说明中明确差异原因（电池体系、项目策略、客户定制）。

## 适用范围

当需要适配 gauge 硬件配置时使用本模板。

## 适配分流（先判断）

- 平台 gauge（MTK 平台通用 gauge 框架）：
  - 走本模板全文（含 `mtk_battery.c` 解析链、`battery_prop/dim2_ext/table` 参数规则）。
- 三方 gauge（非平台通用 gauge 方案）：
  - 适配方法不同，不能直接套用本模板的参数固化规则。
  - 先确认三方驱动与节点入口（驱动文件、`compatible`、DTS 节点、Kconfig/Makefile）。
  - LK 阶段宏控（必须检查）：
    - 在 `vendor/mediatek/proprietary/bootable/bootloader/lk2/project/<board>.mk` 打开：
      - `TRAN_DUAL_BATTERY = yes`
      - `TRAN_SINGLE_GAUGE = yes`
  - 再按三方驱动实际解析字段单独出适配清单。

## 芯片平台差异分层（按平台生成模板）

- 生成原则：
  - 先按芯片平台选择对应基准 `*_battery_prop.dtsi` 与 `*_battery_prop_dim2_ext.dtsi`。
  - 模板先生成“平台通用项”，再按平台补“差异项”。
  - 仅当命中该芯片平台时才生成该平台差异项。
  - 所有平台差异项都要标注：`[基于历史项目 copy，需项目复核]`。

- `battery_prop.dtsi` 平台差异（6.12 基准目录）：
  - 基础平台（如 `mt6789`/`mt6855` 等）：以核心字段为主（无 `vbat2-det-*` 与 `bat-voltage-low-bound` 组）。
  - 增强平台（如 `mt6858`/`mt6881`/`mt6993`）新增差异项：
    - `curr-measure-20a`
    - `unit-multiple`
    - `enable-r-ratio`
    - `enable-charging-ratio`
    - `vbat2-det-voltage1` / `vbat2-det-voltage2` / `vbat2-det-voltage3`
    - `bat-voltage-low-bound`
    - `low-tmp-bat-voltage-low-bound`
  - 变体平台（如 `mt6991_rl`）再新增：
    - `enable-r-learning`（及同类 RL 扩展项）

- `battery_prop_dim2_ext.dtsi` 平台差异：
  - 短版结构（基础平台）：到 `g-fg-charge-pseudo100` 为主。
  - 长版结构（增强平台，如 `mt6858`/`mt6881`/`mt6993`）新增差异项：
    - `g-q-max-row/col` + `g-q-max`
    - `g-q-max-h-current-row/col` + `g-q-max-h-current`
    - `g-iavg-th-raw/col` + `g-iavg-th`
    - `battery{n}-r-ratio-profile-t{m}-num/value`
    - `battery{n}-charging-r-ratio-profile-t{m}-num/value`

典型耦合点：
- Gauge DTSI 节点与默认参数
- 内核构建与可选模块打包
- 仅在存在硬件引脚依赖时涉及 DWS/pinctrl
- 按需对齐 bootloader 侧依赖

## 必填输入

- Gauge 型号：
- 接口与地址：
- 测量与校准输入：
- 关联电池与 charger 依赖：
- 目标项目路径（kernel、lk、preloader）：

## 适配骨架

### 1) Kernel DTSI
- 新增或更新 gauge 节点
- 填写关键配置属性
- 连接 battery manager 相关依赖

### 2) Kernel Build and Packaging
- 更新 Kconfig 与 Makefile 条目
- 按需补充 ko csv 打包

### 3) DWS and Pinctrl
- 按需配置总线与中断引脚

### 4) Bootloader（LK / Preloader）：gauge 相关宏控（不含具体 gauge 器件 `CONFIG_*`）

以下常见于 Tran 项目在 **`lk2/project/<BOARD>.mk`**（或工程等价入口）中的开关，与 **内核 `&mtk_gauge` / 三方 gauge 驱动** 不是同一层配置；适配时不要与器件宏混淆。

| 宏 | 含义与典型适用范围 |
|---|---|
| `TRAN_SINGLE_GAUGE` | **三方电量计 / 非平台默认 gauge 路径** 才可能需要；平台 MTK gauge + 单电池主流项目 **一般不开**。 |
| `TRAN_DUAL_BATTERY` | **双电芯 / 双电池架构** 或配套三方方案才可能需要；单电池 **一般不开**。 |
| `TRAN_LOW_BATTERY_SUPPORT` | 与 **电池是否支持低电启动**（极低电量下开机/引导策略）等产品定义相关；**与是否三方 gauge 无必然关系**。 |

**执行纪律**

- 若无法从 DTS（`tc_gauge` / `mtk_gauge` / 三方节点）与 `tran_custom.config` **断定**是平台 gauge 还是三方 gauge：**必须先反问用户**再改 LK 宏。
- 若短期无法确认但需保留占位：**可在对应 `.mk` 中加简短注释**（宏语义 + 「待项目确认 gauge 类型 / 电池低启规格」），避免后人误抄参考机。
- Preloader 侧也可能出现 `TRAN_LOW_BATTERY_SUPPORT` 等与启动相关的开关；是否与 LK 一致需按 **同一产品定义** 核对，不要默认三地（preloader / lk / kernel）各自为政。

## DTSI 配置项含义（固化字典）

> 用途：后续问答直接复用本节，不再重复做代码反查。  
> 适用文件：`*battery_prop*.dtsi`、`*battery_prop_dim2_ext*.dtsi`、`*battery_table*.dtsi`。  
> 解析入口（固定）：`drivers/power/supply/mtk_battery.c` 中 `fg_custom_init_from_dts()`、`fg_read_dts_val()`、`fg_read_dts_val_by_idx()`。

### A) `battery_prop.dtsi`（`&mtk_gauge`）字段字典

| 字段 | 含义 | 固化级别 |
|---|---|---|
| `difference-fullocv-ith` | 满电 OCV 电流阈值差分；满电时若电流低于此值会触发校准，固化为 `200` | 高 |
| `shutdown-1-time` | 低电量关机等待时间策略参数，通用配置固定为 `60`（低优先级参数） | 中（项目差异大） |
| `keep-100-percent` | 是否在 UI 显示 100% 时额外保持一段时间，固定为 `1` | 高 |
| `PSEUDO1_EN` | 1% 电量藏电功能使能：硅负极电池配置为 `1`，非硅负极配置为 `0` | 低（项目定制） |
| `curr-measure-20a` | 电流测量量程/模式开关，配置为 `0` | 高 |
| `unit-multiple` | 量测单位倍率缩放，配置为 `1` | 高 |
| `embedded-sel` | embedded 电池选择开关，配置为 `1` | 中（项目复核） |
| `r-fg-value` | FG 等效采样电阻参数 | 高（值项目化） |
| `pmic-shutdown-current` | PMIC 关机电流阈值，配置为 `20` | 高 |
| `fg-meter-resistance` | FG 回路电阻补偿，默认 `70` | 高 |
| `car-tune-value` | 库仑计量校准系数，默认 `100` | 高 |
| `pmic-min-vol` | 关机电压：硅负极配置 `3000`；非硅负极配置 `3400` 或 `3350` | 高 |
| `shutdown-gauge0-voltage` | pseudo 1% 功能认定 0% 电量时的电压阈值：硅负极与 `pmic-min-vol` 一致；非硅负极按 `pmic-min-vol + 50` 配置 | 中（项目复核） |
| `BAT_VOLTAGE_LOW_BOUND` | `vbat` 低于此值时，将 `UISOC` 向 `1%` 追平 | 低（项目定制） |
| `poweron-system-iboot` | 开机校准时假定的 `isys`，默认 `500`，会被 `g-pon-sys-iboot` 替换 | 高 |
| `temperature-t0..t4` | 需要根据电池表确定；电池曲线按哪些温度分档，影响 `battery*-profile-t*` 每档的适用温度 | 高 |
| `temperature-t5` | 扩展低温温区 | 中（可选） |
| `g-fg-pseudo100-t0..t4` | 各温区 pseudo100 设定 | 高 |
| `g-fg-pseudo100-t5` | 扩展温区 pseudo100 | 中（可选） |
| `q-max-sys-voltage-bat0..3` | 电池电压达到该值时，触发 1% 藏电显示（按电池 ID 分档）；配置与 `shutdown-gauge0-voltage` 保持一致 | 高 |
| `com-fg-meter-resistance` | FG 电阻补偿附加项 | 中 |
| `com-r-fg-value` | RFG 补偿附加项 | 高 |
| `enable-tmp-intr-suspend` | suspend 时是否使能温度中断；一般配置为 `0` | 高 |
| `active-table` | 需要根据电池表确定；其值影响 `temperature-t*` 与 `battery*-profile-t*` 的数量，也影响 `g-pmic-min-vol`、`g-pon-sys-iboot`、`g-qmax-sys`、`g-fg-pseudo100`、`g-fg-charge-pseudo100` 实际生效行数 | 高 |
| `multi-temp-gauge0` | 启用多温表模型 | 高 |
| `rbat-pull-up-volt` | NTC 上拉电压设定；规则：优先到 `kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/bat_setting` 下查找同名 `*_battery_prop.dtsi`，读取该值并同步到项目配置 | 高 |
| `enable-r-ratio` | 放电 R-ratio 补偿开关 | 中（6.1 常缺省） |
| `enable-charging-ratio` | 充电 R-ratio 补偿开关 | 中（6.1 常缺省） |
| `io-channels` / `io-channel-names` | IIO 采样通道绑定（含 batteryID 通道） | 低（硬件相关） |
| `tran_Q_diff` | Transsion 项目 qmax 覆盖参数 | 低（分支定制） |
| `VIR_OLDOCV_DIFF_EMB` / `_LT` | 虚拟 OCV 修正阈值 | 低（分支定制） |
| `UI_LOW_LIMIT_*`、`SHUTDOWN_GAUGE1_*` 等大写块 | ODM 项目扩展的 UI/关机策略参数 | 低（项目定制） |

### B) `battery_prop_dim2_ext.dtsi`（二维扩展表）字段字典

> 固化的是“结构”，不是具体曲线数值。

| 字段组 | 含义 | 固化级别 |
|---|---|---|
| `g-pmic-min-vol-row/col` + `g-pmic-min-vol` | 关机电压二维表（列是不同 battery ID，行是不同温度档） | 高 |
| `g-pon-sys-iboot-row/col` + `g-pon-sys-iboot` | 开机校准 `isys` 二维表（列是不同 battery ID，行是不同温度档），恒定全为 `5000` | 高 |
| `g-qmax-sys-vol-row/col` + `g-qmax-sys-vol` | 1% 藏电显示电压阈值二维表（列是不同 battery ID，行是不同温度档；按相同行列位置比 `g-pmic-min-vol` 高 `1000`） | 高 |
| `g-fg-pseudo100-row/col` + `g-fg-pseudo100` | 藏电量二维表（列是不同 battery ID，行是不同温度档）；默认全为 `100`，需用户根据充电满百时间和截止时间手动配置 | 高 |
| `g-fg-charge-pseudo100-row/col` + `g-fg-charge-pseudo100` | 充电态 pseudo100 二维表（列是不同 battery ID，行是不同温度档） | 高 |
| `g-q-max-row/col` + `g-q-max` | qmax 二维表（列是不同 battery ID，行是不同温度档） | 高 |
| `g-q-max-h-current-row/col` + `g-q-max-h-current` | 大电流场景 qmax 二维表（列是不同 battery ID，行是不同温度档） | 高 |
| `g-iavg-th-raw/col` + `g-iavg-th` | 平均电流阈值二维表（列是不同 battery ID，行是不同温度档） | 高 |
| `battery{n}-r-ratio-profile-t{m}-num/value` | 放电 R-ratio 曲线 | 高（结构） |
| `battery{n}-charging-r-ratio-profile-t{m}-num/value` | 充电 R-ratio 曲线 | 高（结构） |

### C) `battery_table.dtsi`（主曲线）字段字典

| 字段 | 含义 | 固化级别 |
|---|---|---|
| `battery{n}-profile-t{m}-num` | 温区 `t{m}` 曲线**数据行数**（必须与下方 `< ... >` 内**非空行**一致，含末行重复点） | 高 |
| `battery{n}-profile-t{m}-col` | 每行**列数**（常见 3 或 4），需与每行 field 数一致 | 中（不可写死） |
| `battery{n}-profile-t{m}` | 主 profile 曲线数据块 | 高（结构） |

**必做一致性校验（低阶错误）**

- 对每个 `battery{n}-profile-t{m}`：在属性值角括号内，**统计数据行数**（只计 `...>` 与 `>;` 之间的行，**不计**角括号自身）。  
- **`battery{n}-profile-t{m}-num` 必须等于该行数**。从参考机/老树 copy 时常见的翻车：**`-num` 仍是模板默认值（如 100），实际粘贴了更多或更少行**（例如 LJ9 曾出现 **t5 声明 100 行、实为 122 行**）。  
- 若不确定是否含尾部重复点行：以 **老树同名文件** 为基准对齐 `-num` 与行数；老树也没有时再让用户确认电池厂交付表。

## 固化策略（后续问答统一口径）

- 高：直接进入模板必填项。
- 中：进入模板推荐项，给默认值并注明“项目复核”。
- 低：进入模板可选项，只在命中对应平台/项目时开启。
- 命名统一：模板主风格采用 `kebab-case`；若项目已有 `UPPER_SNAKE_CASE` 扩展，保留兼容块并避免同语义重复赋值。
- 禁止写死：`shutdown-1-time`、`battery{n}-profile-t{m}-col`、各类曲线数据值必须项目化确认。
- **`battery{n}-profile-t{m}-num` 禁止与数据块行数脱节**：迁移或粘贴曲线后必须人工或脚本数行核对。

## 输出模板

- 需修改文件：
- 关键配置更新：
- 依赖映射：
- 平台差异项标注（必须）：
  - 标注格式：`[基于历史项目 copy，需项目复核]`
- 验证清单：
  - 编译通过
  - gauge 注册成功
  - 关键属性读取链路可用
  - LK：若未使用三方 gauge / 双电，`TRAN_SINGLE_GAUGE`、`TRAN_DUAL_BATTERY` 应为关闭或未定义；`TRAN_LOW_BATTERY_SUPPORT` 与电池低启规格一致
  - **`battery_table.dtsi`**：每个温区 `battery{n}-profile-t{m}-num` == 对应 `< >` 数据块**实际行数**

## 边界

- 本模板用于配置适配，不做运行期算法修改。
- 若问题是运行期测量异常诊断，先走分析类技能。
