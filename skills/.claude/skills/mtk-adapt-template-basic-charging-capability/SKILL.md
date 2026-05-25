---
name: mtk-adapt-template-basic-charging-capability
description: MTK 基本充电能力参数适配模板。LK tc_charger_lk.dtsi 强约束、tran_otg 常态保留、`temp_forecast`/`pa_temp_gap` 默认 500 等见正文。老 mediatek `&charger`→`tc,charger` 的 DROP/`single_batt` USER/`dynamic_mivr_vol` 等见 **`transsion-charger-dtsi-driver-bridge`**「老 `&charger`」节。`tc_charger.dtsi`：`ftm_cp_num`（CP 颗数）、`batt_ht/lt`+vote+`kpoc_batt_*`+`*_dis_chg` 模板与电池温区待对齐（TODO）、`&u2port0` 眼图参数从老树同步、`&mt6375_chg` 禁用随器件适配。其余含电压电流阈值、温区策略、满充与保护策略等。
---

# MTK 模板：基本充电能力参数适配

## 适用范围

用于“非器件替换”场景的参数级适配，包括但不限于：
- 充电电流/电压能力（USB/AC/PD/主机口）
- 温区与降额策略
- 满充判据与尾电流策略
- 低电压/关机阈值
- UI 电量显示策略（如 1% 藏电、满百保持）

不用于：
- 新增/更换 charger IC、PD IC、charge pump、gauge 器件（走器件模板）
- 运行期 bug 根因分析（走分析类 skill）

## 最小输入

- 项目名与完整项目路径：
- 平台与版本（A16/W/6.12、A15/V/6.6、A14/U/6.1）：
- 参数变更目标列表（字段名 + 目标值/目标行为）：
- 约束来源（电池规格书/客户需求/历史项目）：
- 生效范围（kernel/lk/preloader）：

## 通用执行步骤

1. 先定位参数归属层（kernel dtsi / lk dtsi / preloader 宏）。
2. 以平台基准配置为起点（同平台同名基线文件）。
3. 按目标值落地到项目配置，记录与基线差异。
4. 标注参数来源：
   - 固化默认
   - 基于历史项目 copy（需复核）
   - 由电池表/规格书给出
5. 输出验证清单（编译、节点解析、关键行为观测点）。

## `tc_charger_lk.dtsi` 强约束（LK 层 · 参数适配）

属 **基本充电能力参数** 在 **LK** 的落点（路径见 **`mtk-adapt-template-device-charger-ic`** 中 **`tc_charger_lk.dtsi` 路径规则**，以及 **`mtk-adapt-upgrade-branch-orchestrator`** 路径解析纪律 §1 第 5 步）。老项目升级或新分支对齐时，下列项为本 skill **项目基线强约束**；若电池规格或法规与本基线冲突，须在会话中 **点名冲突** 并由项目书面裁决。

### 必配项（数值与原因）

| 属性 | 强约束值 | 含义 | 老项目常见偏差与变更原因 |
|------|----------|------|--------------------------|
| `fast-charge-voltage` | **`<2500000>`** | **2.5 V**（µV） | **必须**。老项目常为 **2.3 V**（`<2300000>`）。需改为 **2.5 V**：**测试要求约 5 s 内亮屏**，缩短预充阶段、缓解预充时间过长。 |
| `ac-charger-current` | **`<2000000>`** | **2 A**（µA） | **必须与下列输入电流成对满足 2 A 强要求**。 |
| `ac-charger-input-current` | **`<2000000>`** | **2 A**（µA） | **必须与 `ac-charger-current` 同为 2 A**。 |
| `non-std-ac-charger-current` | **`<1200000>`** | **1.2 A**（µA） | 非标 AC 场景默认可用电流 **1.2 A**。 |
| `temp-t4-threshold` | **`<56>`** | 最高温档门槛（°C，与平台节点定义一致） | 老项目常配 **50**。易引起 **高于 50 °C 后策略叠加导致反复重启**；将最高温档门槛 **提高至 56 °C** 以规避该现象。 |

### 属性命名说明

- 若目标平台 **`tc_charger_lk.dtsi`** 使用不同属性名（例如与 kernel `tc_charger.dtsi` 对齐的别名），以 **平台基准文件** 与 **LK 侧实际 binding** 为准；**语义上** AC 双 **2 A**、非标 **1.2 A**、预充电压 **2.5 V**、`temp-t4-threshold` **56 °C** 不变。

## `tc_charger.dtsi` 模板草案（A16/A15 通用骨架）

### 1) 固定骨架（必须生成）

- 顶层结构：`&odm { ... }` + `&charger { ... }`
- `&odm` 必配基础能力节点：
  - `tran_otg`
  - `tc_chgtype`
  - `tc_pmic`
  - `tc_gauge`
  - `tc_misc`
  - `tc_lcd`
  - `tc_tcpc`
  - 算法骨架：`tc_pe2`、`tc_30`、`tc_hvdcp20`、`tc_pd`
- `&charger` 必配基础开关：
  - `enable_sw_jeita`
  - `enable_hv_charging`
  - `enable_sw_safety_timer`
  - `enable_dynamic_mivr`
  - `enable_ir_comp`

### 2) 平台差异固定规则（必须执行）

- extcon 选型：
  - A16：优先选用 `tran usb extcon`
  - A15/A14：选用 `mtk usb extcon`
- `charger = <&tc_chgtype>;` 联动保持一致，至少覆盖：
  - `&extcon_usb`
  - `&mtk_gauge`
  - （按项目存在性）`&mt6375_typec` / `&mt6720_typec`
  - （A16 推荐）`&battery_manager`

### 2b) 同文件充电周边：`&u2port0` USB2 眼图、`&mt6375_chg` 开关（柱 2 / 器件适配）

- **`&u2port0 { … }`**（**`mediatek,eye-vrt`、`mediatek,eye-term`、`mediatek,rev6`、`mediatek,discth`** 及 **`mediatek,eye-vrt-host` / `eye-term-host` / `rev6-host`** 等）  
  - **来源**：在 **老分支** **`tran_charger.dtsi`**，或与充电同批 include 的 **`<project_full>.dts` / 板级 dtsi** 中 **`rg` `u2port0`、`mediatek,eye-vrt`** 等，将**已存在且经量产验证**的整段属性 **同步到新树** `tc_charger.dtsi` **或** 平台规定的 **fragment**（**勿**在无老树依据时凭空填数）。  
  - **与 SoC / PHY 版本强相关**，合入后 **`[REVIEW]`** USB2 眼图与插拔稳定性。更细的图与 **extcon graph** 纪律见 **`tran-projects-config-migrate-dtsi-dws`**（**`&u2port0` / `&extcon_usb`** 小节）。

- **`&mt6375_chg { status = "disabled"; }`**（或其它 PMIC 默认 charger 节点的 **`status`**）  
  - **归属**：由 **`mtk-adapt-template-device-charger-ic`** 等 **器件适配** 结论与 **原理图 / BOM** 决定，**不是**「基本能力参数」里独立发明的开关。  
  - **常见写法**：新 KDM 与 **`tc_charger`** 主路径并存时，将 **未使用** 的 **`mt6375_chg`** 等节点 **`status = "disabled"`**，避免与真实充电栈 probe 冲突。执行时与 **`tran-projects-config-migrate-dtsi-dws`** 中 **「`&mt6375_chg` 是否禁用」** 条保持一致。

### 3) 参数化块（推荐默认，可覆盖）

- `support_alg`（建议默认五算法，按项目裁剪）：
  - `"pe5", "hvdcp20", "pd", "tc30", "pe20"`
- 基础电流能力（推荐起始）：
  - `sdp_* = 500000`
  - `cdp_* = 1500000`
  - `dcp_* = 2000000`
  - `nonstd_* = 1200000`
- OVP/MIVR/限流：
  - `dynamic_mivr_vol`
  - `charger_voltage_ovp`
  - `max_input_current_limit` / `max_charging_current_limit`
- 温区限流与曲线（必须结合电池规格）：
  - `tbat_*` / `tpcb_*` / `tpa_*`
  - **`ftm_cp_num`**（**CP 颗数**，详见 **§C `ftm_cp_num`（CP 颗数）**）
  - 高低温保护与投票参数（**`*_vote_*` 三向量** 见 **§C 温度限流与保护组** 模板）：
    - `batt_ht_temp` / `batt_ht_rec_temp` / `batt_ht_code` / `batt_ht_vote_hiz` / `batt_ht_vote_discharge` / `batt_ht_vote_icon`
    - `batt_lt_temp` / `batt_lt_rec_temp` / `batt_lt_code` / `batt_lt_vote_hiz` / `batt_lt_vote_discharge` / `batt_lt_vote_icon`
    - `kpoc_batt_ht_*` / `kpoc_batt_lt_*`（与上对称，含 **vote**）
    - `batt_ht_temp_dis_chg` / `batt_ht_code_dis_chg` / `batt_lt_temp_dis_chg` / `batt_lt_code_dis_chg`
  - `single_batt_level` 与 `single_batt_level_*`

### 4) 客制化块（按需启用）

**合并摘录**：经 **`mtk-adapt-template-router`** 柱 3 做「客制化特性」落盘时，**默认以用户口述为准**（见 **`transsion-sunmao40-customization-features-adapt`** **RULE-0**）；可选 **`pillar3-customization-input.md`**；可优先 **`Read` 同文件** **RULE-4**（与本节规则、示例同步）；**温区、算法、LK `tc_charger_lk.dtsi` 强约束等柱 2 条文仍以本 skill 全文为准。**

- `water_detect` / `tc_audio`：
  - 归类为“防水检测/进水检测/进液检测”
  - 默认不固化，按项目需求启用
  - 标注：`[基于历史项目 copy，需项目复核]`
- `wireless_*`：
  - 归类为无线充电相关配置
  - 默认不固化，按项目需求启用
  - 标注：`[基于历史项目 copy，需项目复核]`
- 其他客制化（如 `support_enhance_mode`、`support_real_soc_decimal`、`support_long_life_recharger`、`support_allround_bypass`）同样按需启用并标注复核来源。
- 客制化特性模板保留规则（必须执行）：
  - 客制化开关或参数必须写进模板中（即使默认不启用）。
  - 默认采用“注释保留”形式，便于按项目解注。
  - 每个开关/参数必须在同一行或上一行注释标明“对应哪个客制化特性”。
  - 注释格式建议：`// 客制化特性-<特性名称>`

#### 客制化特性保留清单（默认注释示例）

```dts
/* &charger 客制化开关（默认注释保留） */
/* support_enhance_mode; */          // 客制化特性-低功率充电增强
/* support_real_soc_decimal; */      // 客制化特性-电量小数点上报
/* support_long_life_recharger; */   // 客制化特性-长寿命复充
/* support_allround_bypass; */       // 客制化特性-全场景旁路充电
/* support_bat_self_repair; */       // 客制化特性-电池自修复

/* long_life_rechg_time = <180>; */          // 客制化特性-长寿命复充
/* bat_repair_cycle_threshold = <200>; */    // 客制化特性-电池自修复
/* bat_repair_done_uisoc = <5>; */           // 客制化特性-电池自修复
/* bat_repair_done_vbat = <3400>; */         // 客制化特性-电池自修复
/* health_percent_cycle_table = <...>; */    // 客制化特性-电池自修复
/* health_percent_add_table = <...>; */      // 客制化特性-电池自修复

/* &odm 客制化节点（默认注释保留） */
/* tc_trancare: tc_trancare { ... }; */      // 客制化特性-充电大数据埋点
/* port_corrosion: port_corrosion { ... }; */ // 客制化特性-端口防腐蚀
/* phy_det: phy_det { ... }; */              // 客制化特性-端口检测
/* water_detect: water_detect { ... }; */    // 客制化特性-防水/进水/进液检测
/* tc_audio: tc_audio { ... }; */            // 客制化特性-防水/进水/进液检测（音频口联动）
/* wireless_manager: wireless_manager { ... }; */ // 客制化特性-无线充电
/* tc_wireless_ta: tc_wireless_ta { ... }; */     // 客制化特性-无线充电
```

### 5) 标注规范

- 所有“非平台通用固定值”的差异项必须标注：
  - `[基于历史项目 copy，需项目复核]`

## `tc_charger.dtsi` 节点作用字典（补充）

### A) `&odm` 下基础能力节点

- `tran_otg`
  - 作用：OTG 反向 5V 供电与反向充电能力控制（含温控与限流）。
  - 关键参数：`pd_reverse_chg_support`、`tc_otg_boost_curr_max/min`、`otg_reverse_chg_*`、`otg_revercharge_limit_temp`。
  - **常态保留**：无单独规格否决时，**以下属性整组作为默认** 写入 `tran_otg`（老→新补全、绿场新建均优先对齐本节，再标 **`[REVIEW]`** 实机核对）；与 **`transsion-charger-dtsi-driver-bridge`**「`tran_otg` 迁移工作流」并存。
  - 功率档：`tc_otg_boost_curr_max` **10 W 用 `<2000000>`**，**6 W 用 `<1200000>`**；其余温控门限与扣减保持本节数值除非产品另有要求。

### `tran_otg` 常态保留（推荐默认片段）

下列写入 **`&odm`** 下 **`tran_otg`** 节点内（层级与 label 以平台/baseline 为准）。**`compatible = "tran,otg_fun"`** 必须保留（见 bridge）。

```dts
/* PD 反向充电 + Boost 温控：常态保留 */
pd_reverse_chg_support;
otg_revercharge_limit_temp = <45>;
tc_otg_boost_curr_max = <2000000>; /* 10W: 2000000, 6W: 1200000 */
tc_otg_boost_curr_min = <500000>;
otg_reverse_chg_curr_lmt = <1000000>;
otg_reverse_chg_limit_temp_step1 = <42>;
otg_reverse_chg_recovery_area = <3>;
```

- **说明**：`otg_revercharge_limit_temp`（45 °C）与 `otg_reverse_chg_limit_temp_step1`（42 °C）、`otg_reverse_chg_recovery_area`（3 °C）构成反向充电 **降额 / 恢复** 迟滞；`otg_reverse_chg_curr_lmt` 与 `tc_otg_boost_curr_max` 组合定义第二段温区下的有效上限（驱动语义见 **`transsion-charger-dtsi-driver-bridge`** `tran_otg` 属性表）。

- `tc_trancare`
  - 作用：充电大数据埋点/上报能力。
  - 关键参数：通常无复杂数值，主要是节点启用。
  - 默认建议：按产品要求启用，属于客制化能力。

- `tc_chgtype`
  - 作用：BC12 识别、PD 事件接收与充电类型中枢桥接。
  - 关键参数：`phys`、`phy-names`、`usb`（及部分分支的 `charger`/retry 开关）。
  - 默认建议：必须启用；引用对象按项目 USB/charger 架构复核。

- `tc_pmic`
  - 作用：低压场景下 PMIC vbus/ADC 采样通道封装。
  - 关键参数：`io-channels`、`io-channel-names`。
  - 默认建议：建议启用，通道号按硬件与 PMIC 方案对齐。

- `tc_gauge`
  - 作用：封装 gauge 接口并桥接 `&mtk_gauge`。
  - 关键参数：`gauge = <&...>`。
  - 配置规则：需先判断电量计类型；平台电量计配置为 `gauge = <&mtk_gauge>`，三方电量计先留空，待后续补充同步规则。
  - 默认建议：节点必须启用，`gauge` 引用按电量计类型分流配置。

- `tc_misc`
  - 作用：充电中间层杂项接口（如 TUSB 温度、辅助检测）。
  - 关键参数：`io-channels`、`tusb_div_res`、`tusb_div_vol`、`min_tusb_temp`、`max_tusb_temp`。
  - 默认建议：建议启用；其中 `io-channels` 不是固定值，需要从硬件原理图获取，温度相关参数按硬件分压网络复核。

- `tc_lcd`
  - 作用：亮灭屏状态通知给充电策略层。
  - 关键参数：通常为开关类。
  - 默认建议：建议保留。

- `tc_tcpc`
  - 作用：承接 TCPM/Type-C/PD 状态并传递给 `tc_chgtype`。
  - 关键参数：通常为节点使能。
  - 默认建议：必须启用（有 Type-C/PD 场景时）。

- `tc_auto_test`
  - 作用：自动化测试相关接口。
  - 关键参数：通常为节点使能。
  - 默认建议：默认保留。

- `tc_adapter_control`
  - 作用：适配器控制（部分项目未实际使用）。
  - 关键参数：`polling_interval`。
  - 默认建议：按项目打包情况决定是否保留。

### B) `&odm` 下算法与策略节点

- `tc_pe2` / `tc_30` / `tc_hvdcp20` / `tc_pd`
  - 作用：对应 PE2.0 / TC3.0 / HVDCP2.0 / PD 算法参数承载节点。
  - 关键参数：`ta_ichg_level_threshold`、`vbat_threshold`、`chr_volt*`、`min_charger_voltage`、`charger_current_limit`。
  - 默认建议：节点骨架保留，是否启用与 `support_alg` 严格一致。

- `pid_chg`
  - 作用：多场景温控/功耗闭环调节（PID）。
  - 关键参数：`pid_array`、`target_temp_array`、`polling_interval` 等。
  - 默认建议：属策略类参数，默认可保留结构，数值需项目复核。

- `ambient_detect`
  - 作用：环温检测与功率/温升联动策略。
  - 关键参数：`ambient_*`、`power_level`、`power_delta_temp`。
  - 默认建议：按项目需求启用并复核。

- `temp_forecast`
  - 作用：温度拟合预测，用于提前调节充电策略。
  - 关键参数：`orgin_rate`、`max_temp_diff`、`max_comp_temp`、`pa_temp_gap`。
  - **`pa_temp_gap`**：老树无此项或新建节点时 **默认 `pa_temp_gap = <500>`**（单位与 **`tc_temp_forecast*.c` parse_dt** 一致，一般为与预测相关的间隔量）；若目标平台已有量产 **`tc_charger.dtsi`** 基准则从其，否则用 **500**。
  - 默认建议：节点按项目启用；除 **`pa_temp_gap` 默认** 外，其余数值仍须结合基准树与产品复核（**`orgin_rate` 勿被参考模板静默覆盖**）。

### C) `&charger` 节点主参数组

- 基础开关组
  - 作用：控制基础充电能力（JEITA/HV/safety timer/dynamic mivr/IR comp）。
  - 关键参数：`enable_sw_jeita`、`enable_hv_charging`、`enable_sw_safety_timer`、`enable_dynamic_mivr`、`enable_ir_comp`、`support_hardware_ir_comp`。
  - 默认建议：默认开启。

- IR 补偿与调试基础组
  - 作用：补偿充电路径压降并控制日志/轮询策略。
  - 关键参数：`r_comp`、`v_comp_max`、`log_level`、`polling_interval`。
  - 默认建议：给平台推荐默认，按项目热设计与调试需求复核。

- 算法选择与最低输入能力组
  - 作用：声明启用算法并定义基础入门电压电流门槛。
  - 关键参数：`support_alg`、`min_charger_voltage`、`min_charger_current`。
  - 默认建议：`support_alg` 与 `tc_pe2/tc_30/tc_hvdcp20/tc_pd` 节点一致，门槛值按项目功率档复核。

- **`ftm_cp_num`（CP 颗数）**
  - 作用：在 **`&charger`** 上声明 **charge pump（CP）器件数量**，与 **多路 DVCHG / 快充编排** 对齐（解析以 **`tc_charger.c`** 及绑定为准）。
  - 写法：**`ftm_cp_num = <N>;`**，**N** = **实装 CP 颗数**（例：单 CP **`<1>`**，双 CP **`<2>`**）。须与 **BOM、`tc_pe5` 单/双 CP 拓扑** 及产品定义一致；**禁止**盲抄参考模板与实机不符的 **N**。
  - 默认建议：柱 2 合入前 **`Read`** 目标树 **`tc_charger`** 的 **DT 属性表**，确认属性名仍为 **`ftm_cp_num`**。

- 输入/充电电流能力组
  - 作用：定义 SDP/CDP/DCP/非标口及总限流能力。
  - 关键参数：`sdp_*`、`cdp_*`、`dcp_*`、`nonstd_*`、`max_*_limit`。
  - 默认建议：给推荐默认，按项目功率档复核。

- OVP/MIVR 与充电时长组
  - 作用：定义输入保护上限、动态 MIVR 档位与最长充电时长。
  - 关键参数：`charger_voltage_ovp`、`dynamic_mivr_vol`、`max_charging_time`、`swchg_hw_eoc_max`。
  - 默认建议：按适配器能力、硬件耐压与平台策略复核。

- EOC 与老化策略组
  - 作用：定义截止策略、老化区间与健康度衰减模型。
  - 关键参数：`eoc_scheme`、`aging_start_uisoc`、`aging_stop_uisoc`、`bat_health_cycle_base`、`bat_health_dec_times`。
  - 默认建议：按项目寿命目标与售后策略复核。

- KOM/客制电量管控组
  - 作用：定义特定版本（如 KOM）下的电量区间管控阈值。
  - 关键参数：`kom_start_uisoc`、`kom_stop_uisoc`。
  - 默认建议：仅在命中该客制需求时启用。

- 温度限流与保护组
  - 作用：定义 **`tbat_*` / `tpcb_*` / `tpa_*`** 温区限流曲线，以及 **电池高温 / 低温 / KPOC 镜像 / 放电路径** 下的 **门限、恢复温度、事件码（`code`）与 vote（HIZ、放电、图标等）**；**`*_dis_chg`** 为 **放电/非充电路径** 下的温区与码表。
  - 关键参数：`tbat_*`、`tpcb_*`、`tpa_*`；**`batt_ht_*` / `batt_lt_*`**（含 **`*_vote_hiz`、`*_vote_discharge`、`*_vote_icon`**）；**`kpoc_batt_ht_*` / `kpoc_batt_lt_*`**（对称三组 vote）；**`batt_ht_temp_dis_chg` / `batt_ht_code_dis_chg` / `batt_lt_temp_dis_chg` / `batt_lt_code_dis_chg`**。
  - **模板（柱 2 先按结构落盘，再与电池域对齐）**：下列 **键名与向量长度** 与 **`cl6k_h898` 等量产 `tc_charger.dtsi`** 一致时可作 **首版骨架**；**各元具体数值与 `code` 位定义** 须以 **电池规格书可充温区、JEITA、停充/告警语义** 及 **`Read tc_charger.c`** 为准。**与「电池支持的充电区间」及电池表的一致性** 仍属 **跨域核对 —— `[TODO]` 待做**：须与 **电池表 / `single_batt_level_*` / gauge 策略** 联调后再定稿，本模板 **不**代替电池 skill 给最终数。

```dts
	ftm_cp_num = <2>;

	batt_ht_temp = <53 55 58>;
	batt_ht_rec_temp = <0 54 54>;
	batt_ht_code = <0 (1 << 11) (1 << 10)>;
	batt_ht_vote_hiz = <0 0 0>;
	batt_ht_vote_discharge = <0 1 1>;
	batt_ht_vote_icon = <0 1 1>;

	batt_lt_temp = <0 (-19) (-19)>;
	batt_lt_rec_temp = <0 (-17) (-17)>;
	batt_lt_code = <0  0  (1 << 7 | 1 << 12)>;
	batt_lt_vote_hiz = <0 0 0>;
	batt_lt_vote_discharge = <0 1 1>;
	batt_lt_vote_icon = <0 1 1>;

	kpoc_batt_ht_temp = <53 55 58>;
	kpoc_batt_ht_rec_temp = <0 54 54>;
	kpoc_batt_ht_code = <0 (1 << 11) (1 << 10)>;
	kpoc_batt_ht_vote_hiz = <0 0 0>;
	kpoc_batt_ht_vote_discharge = <0 1 1>;
	kpoc_batt_ht_vote_icon = <0 1 1>;

	kpoc_batt_lt_temp = <0 (-19) (-19)>;
	kpoc_batt_lt_rec_temp = <0 (-17) (-17)>;
	kpoc_batt_lt_code = <0  0 (1 << 12 | 1 << 7)>;
	kpoc_batt_lt_vote_hiz = <0 0 0>;
	kpoc_batt_lt_vote_discharge = <0 1 1>;
	kpoc_batt_lt_vote_icon = <0 1 1>;

	batt_ht_temp_dis_chg = <58 58 58>;
	batt_ht_code_dis_chg = <(1 << 10) (1 << 10) (1 << 10)>;
	batt_lt_temp_dis_chg = <(-19) (-19) (-19)>;
	batt_lt_code_dis_chg = <(1 << 7) (1 << 7) (1 << 7)>;
```

  - **说明**：**`vote_*`** 三向量与 **高温/低温档** 一一对应，控制是否 **置 HIZ、允许放电路径、图标提示** 等（精确语义以驱动与产品文案为准，**`[REVIEW]`**）。**`ftm_cp_num`** 与上表同写在 **`&charger`** 内时，**N** 须与 **CP 颗数** 一致（见上 **`ftm_cp_num`** 小节）。
  - 默认建议：老树有等价语义时 **对照迁移**；无老树时 **先用模板占位 + `[TODO]`**，待 **电池 / 热设计** 会签后再改数。

- 过温/过冷硬阈值组
  - 作用：定义绝对高低温边界，配合保护码与投票策略。
  - 关键参数：`batt_over_heat_temp`、`batt_over_cold_temp`。
  - 默认建议：按安全规范与客户要求复核。

- 电池分段充电曲线组
  - 作用：定义不同温度/循环段的 CV/CC/EOC 分段策略。
  - 关键参数：`single_batt_level`、`single_batt_level_*`。
  - 默认建议：必须按电池表输入，不做通用写死。

## `tc_pe50.dtsi` 模板草案（PE5/PE50）

### 1) 固定骨架（必须生成）

- 节点骨架：
  - `compatible = "tc_pe5"`
  - `status = "okay"`
  - `tc_chgtype = <&tc_chgtype>`

### 2) 参数化块（推荐默认，可覆盖）

- 基础节奏与启动门限（推荐默认）：
  - `polling_interval = <500>`
  - `ta_cv_ss_repeat_tmin = <25>`
  - `vbat_cv`、`start_vbat_min`、`start_vbat_max`、`chg_time_max`
- DVCHG 电流与软启动（推荐默认）：
  - `idvchg_pps_term = <1200>`
  - `idvchg_ss_init = <1000>`
  - `idvchg_ss_step = <250>`
  - `idvchg_ss_step1 = <100>`
  - `idvchg_ss_step2 = <50>`
  - `idvchg_ss_step1_vbat = <4000>`
  - `idvchg_ss_step2_vbat = <4200>`
  - `ta_blanking = <400>`
- 线阻/线材与规格切换（需按项目复核）：
  - `rcable_level`、`ita_level`、`cable_capability_level`
  - `vol_diff_level`、`vol_diff_gap = <50>`、`min_ita_gap = <10>`
  - `ita_stable_cnt = <20>`
  - `support_ta`、`support_spec`、`vta_cap_min/max`、`ita_cap_min`、`vbus_max_ovp`
- 运行阈值（推荐默认）：
  - `run_cp_cur`、`run_cp_recovery_gap = <0 500 750 1000>`
  - `run_wls_cp_cur = <0 3000 6000 10000>`
  - `run_wls_cp_recovery_gap = <0 200 400 600>`
- PE50 初始化（推荐默认）：
  - `pe50_vta_init = <5300>`
  - `pe50_ita_init = <3000>`
  - `pe50_wireless_vta_init`、`pe50_wireless_ita_init`
  - `pe50_wireless_pdp_limit`
- 保护与补偿（推荐默认+复核）：
  - `ifod_threshold = <200>`
  - `rsw_min = <20>`
  - `ircmp_rbat`、`ircmp_vclamp`
  - `rechg_tbat_high = <44>`、`rechg_tbat_low`
  - `project_power`、`project_pwr_ratio`
- FFC（必须项目化）：
  - `pe5_ffc_gap = <20 20 20 20 20 20>`
  - `step_ffc_level`
  - `batX_step_ffc_level_N`（按 battery_id 与档位）

### 3) 客制化块（按需启用）

- `wireless_en_dual`、`pe50_wireless_pdp_limit` 等无线强相关项：
  - 默认可保留结构，按项目启用
  - 标注：`[基于历史项目 copy，需项目复核]`
- 注释保留的可选规格/双电池开关：
  - `support_6_2/support_4_1/support_4_2/support_2_1/support_1_1`
  - `support_dual_battery` 与 `step_master/slave_ffc_level_*`
  - 默认注释保留并标注对应客制需求

## `tc_pe50.dtsi` 参数作用字典

- 基础开关与入口
  - 作用：绑定 `tc_pe5` 算法并接入 `tc_chgtype` 事件源。
  - 关键参数：`compatible`、`status`、`tc_chgtype`。

- 基础节奏与启动门限
  - 作用：控制算法循环周期、可进入 PE5 的电池电压窗口、最大运行时长。
  - 关键参数：`polling_interval`、`ta_cv_ss_repeat_tmin`、`vbat_cv`、`start_vbat_min/max`、`chg_time_max`、`wireless_chg_time_max`。

- DVCHG 电流与软启动
  - 作用：控制分压充电软启动电流爬升、终止判据与分段步进阈值。
  - 关键参数：`idvchg_term`、`idvchg_pps_term`、`idvchg_wireless_term`、`idvchg_ss_*`、`idvchg_level_multi`、`ta_blanking`。

- 线阻/线材能力相关
  - 作用：按线阻与线材能力动态限制 TA 电流/压差，避免误判与过冲。
  - 关键参数：`rcable_level`、`ita_level`、`cable_capability_level`、`vol_diff_level`、`vol_diff_gap`、`min_ita_gap`、`ita_stable_cnt`。

- 热限流模板（17 点曲线族）
  - 作用：按 TA/DVCHG/BAT/PCB/PA/系统功耗温度区间限流。
  - 关键参数：`tta_*`、`tdvchg_*`、`tbat_*`、`tpcb_*`、`tpa_*`、`sys_power_*`、`wireless_*`（含 `_h`）。

- 多档参数/多电池参数
  - 作用：按 `battery_id` 与多档等级切换温控/限流模板。
  - 关键参数：`supprot_multi_level_charging`、`support_multi_bat_parameter`、`batX_*_N`。

- 协议与规格能力
  - 作用：定义可用 TA 接口及规格档位、电压电流能力边界与 OVP 上限。
  - 关键参数：`support_ta`、`allow_not_check_ta_status`、`support_spec`、`vta_cap_min/max`、`ita_cap_min`、`vbus_max_ovp`、`default_spec`。

- 运行电流表（多路 CP 角色）
  - 作用：定义 master/slave/third/fourth 在有线/无线下的运行阈值与恢复回差。
  - 关键参数：`run_cp_cur`、`run_cp_recovery_gap`、`run_wls_cp_cur`、`run_wls_cp_recovery_gap`。

- PE5 初始化参数
  - 作用：定义算法启动时 TA 电压/电流初值与无线功率约束。
  - 关键参数：`pe50_vta_init`、`pe50_ita_init`、`pe50_wireless_vta_init`、`pe50_wireless_ita_init`、`pe50_wireless_pdp_limit`、`wireless_en_dual`。

- 保护与补偿参数
  - 作用：异常检测、线路电阻估计、IR 补偿与重充窗口控制。
  - 关键参数：`ifod_threshold`、`rsw_min`、`ircmp_rbat`、`ircmp_vclamp`、`rechg_tbat_high/low`、`project_power`、`project_pwr_ratio`、`pe50_default_vta_step`。

- FFC 分段参数
  - 作用：定义不同温区/循环段下的 FFC 电压-电流-终止策略。
  - 关键参数：`pe5_ffc_gap`、`step_ffc_level`、`batX_step_ffc_level_N`（含 `ffc_temp/ffc_vbat/ffc_ibat/ffc_term/cycle_cnt/rechg_gap/rechg_cur`）。

### D) `single_batt_level*` 生成格式规则（可视化优化）

- 禁止单行展开整段 `single_batt_level_X = <...>;`。
- 必须使用“分段多行”格式，按语义分组并带行内注释：
  - 温度区间
  - 周期区间
  - CV 档位数组
  - CC 档位数组
  - EOC
  - cycle 区间
  - 复充标记
- 每个 `single_batt_level_X` 独立成块，块与块之间空一行。
- 建议统一 4 空格缩进，闭合 `>;` 独立成行。
- 负值必须带括号，例如 `(-20)`、`(-1)`。
- 同一温度区间内，cycle 分段必须覆盖全区间：至少有一档 cycle 上限为 `(-1)`。
- 生成时优先示例格式如下：

```dts
single_batt_level_0 = <
        -20      0          // 温度区间
        -1                   // 预留/版本位
        4530000  4530000  4530000  4530000  4530000  4530000  // CV
        600000   600000   600000   600000   600000   600000   // CC
        300000               // EOC
        0        -1          // cycle 区间
        0                    // 复充标记
>;
```

- 分段补偿与电压间隙组
  - 作用：定义分段切换电压间隙和相关补偿参数。
  - 关键参数：`vbat_gap`（及同类分段补偿项）。
  - 默认建议：与 `single_batt_level_*` 一并按电池表复核。

- 电池自修复组（客制化）
  - 作用：电池自修复策略与健康度补偿。
  - 关键参数：`support_bat_self_repair`、`bat_repair_cycle_threshold`、`bat_repair_done_uisoc`、`bat_repair_done_vbat`、`health_percent_cycle_table`、`health_percent_add_table`。
  - 默认建议：客制化能力，默认按需启用并标注 `[基于历史项目 copy，需项目复核]`。

## 输出模板

- 参数归属分层（kernel/lk/preloader）：
- 需修改文件清单：
- 参数变更表（字段 -> 新值 -> 来源 -> 风险）：
- 与平台基准差异说明：
- 验证点：
  - 编译通过
  - 关键节点属性可读
  - 关键充电行为符合预期

## 自动生成默认值表（无输入条件）

当用户未提供任何项目条件时，按以下规则直接生成一份可评审草稿：

- 默认版本：A16（Android W, kernel 6.12）
- 默认 extcon：tran usb extcon
- 默认 `tc_chgtype` 联动：`&extcon_usb`、`&mtk_gauge`、`&mt6375_typec`、`&battery_manager` 全部指向 `&tc_chgtype`

### 1) 可直接写入的默认值

- `support_alg = "pe5", "hvdcp20", "pd", "tc30", "pe20"`
- `sdp_charger_current = 500000`
- `sdp_input_current = 500000`
- `cdp_charger_current = 1500000`
- `cdp_input_current = 1500000`
- `dcp_charger_current = 2000000`
- `dcp_input_current = 2000000`
- `nonstd_charger_current = 1200000`
- `nonstd_input_current = 1200000`
- `max_input_current_limit = 3000000`
- `max_charging_current_limit = 3600000`
- `min_charger_voltage = 4400000`
- `min_charger_current = 1000000`
- `dynamic_mivr_vol = <4400000 4400000 4400000 4600000>`
- `charger_voltage_ovp = <6500000 10500000 11000000 11000000>`
- `max_charging_time = 72000`
- `r_comp = 15`
- `v_comp_max = 40`
- `log_level = 3`
- `polling_interval = 10`
- **`temp_forecast` / `pa_temp_gap = <500>`**（老树缺省或新写 **`tc,temp_forecast`** 时默认；有量产基准则从基准）

### 2) 生成时保留占位（必须复核）

- `tbat_*`、`tpcb_*`、`tpa_*`
- `batt_ht_*`、`batt_lt_*`、`kpoc_batt_*`、`*_dis_chg`
- `single_batt_level`、`single_batt_level_*`
- `vbat_gap`
- `pid_chg`、`ambient_detect`、`temp_forecast` 其余数值（**`pa_temp_gap` 已见上条默认 500**）

### 3) 客制化块处理

- `water_detect` / `tc_audio`：默认不展开，仅注释占位
- `wireless_*`：默认不展开，仅注释占位
- 所有客制化项统一标注：`[基于历史项目 copy，需项目复核]`

## 边界

- 本模板只处理“参数能力适配”，不替代器件模板。
- 如请求涉及器件驱动/节点新增，回退到器件适配分支。
- **老 5.10 `mediatek,charger`（`tran_charger.dtsi` 等）→ 新 `tc,charger`**：哪些属性 **DROP**、哪些进 **`single_batt`（USER 填）**、**`dynamic_mivr_vol` / `max_charger_voltage` / `pid_chg` 摘取 `ambient_*`** 等 **闸门** 见 **`transsion-charger-dtsi-driver-bridge`** 正文 **「老 `&charger`（mediatek,charger）」**；本 skill **不**重复列 DROP 表。
---

## 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-05-13 | 新增 **`tc_charger_lk.dtsi` 强约束**：`fast-charge-voltage` 2.5 V（相对老项目 2.3 V、5 s 亮屏/预充）；AC 电流双 2 A；非标 1.2 A；`temp-t4-threshold` 56 °C（相对老项目 50 °C 反复重启问题）。 |
| 2026-05-13 | **`tran_otg` 常态保留**：`pd_reverse_chg_support`、`otg_revercharge_limit_temp`、`tc_otg_boost_*`、`otg_reverse_chg_*` 整组默认片段；10 W / 6 W 对 `tc_otg_boost_curr_max` 的取值说明。 |
| 2026-05-13 | **`temp_forecast` / `pa_temp_gap`**：默认 **`<500>`**（老树缺项或新建；有量产基准则从基准）；自动生成草稿列入「可直接写入」；节点字典与占位小节同步。 |
| 2026-05-13 | **`tc_charger.dtsi` 柱 2 补充**：**§2b** `&u2port0` 眼图参数从 **老树 `tran_charger.dtsi` / `<project_full>.dts`** 同步；**`&mt6375_chg`** **`status`** 随 **器件适配**；**§C** **`ftm_cp_num = <N>`**（**N**=CP 颗数）；**高低温 / KPOC / `*_dis_chg` + `vote_*`** 模板与 **`[TODO]`**（与电池可充温区、`single_batt_level_*` 待对齐）。 |
| 2026-05-13 | **边界**：老 **`mediatek,charger`**→**`tc,charger`** 的 DROP / **`single_batt` USER** / **`dynamic_mivr_vol`** 等 **转交 `transsion-charger-dtsi-driver-bridge`**「老 `&charger`」节；**description** 交叉引用。 |

