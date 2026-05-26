---
name: transsion-charger-dtsi-driver-bridge
description: >-
  串联老内核充电驱动源码与老充电 DTSI：逐项说明属性在运行时的含义，并在新 KDM（如 kernel_device_modules-6.12）
  的 tc_charger / transsion 充电栈中定位等价配置项与转换规则。适用于「旧 tran_charger.dtsi / tran_battery」
  「chg_fun」「JEITA」「pcb 热限流」「tran_auto_test→tc_auto_test」「smart_charging→tc_charger 内嵌」「water_detect（transsion, water_detect）scheme 5.10↔6.12 数值映射、bootmode 弃用」「pid_chg（tran,pid_chg_algo→tc,pid_chg_algo）与 ambient_temp/target_temp_array」「ambient_detect / temp_forecast（transsion,*→tc,*）与 pa_temp_gap、machine_gap」  「support_alg 子节点（&pe2/&tc30/&hvdcp20/&pdc→tc_pe2/tc_30/tc_hvdcp20/tc_pd、chr_volt*、vbat_threshold µV）」「extcon_usb（6.12 Tran extcon vs mediatek、charger→tc_chgtype、remote-endpoint 跟芯片基准 dtsi）」、以及「tran_battery_aging 新树可删」类迁移、对照 5.10 与 6.12、或需要写 DTSI 变更说明与 SOURCE/CONVERT 注释时使用。
  含「tran_otg（tran,otg_fun）」仅老→新：compatible 核对、otg_boost_*→tc_otg_boost_* 等改名、老树未配项用模板默认补全与 [REVIEW] 标注。含「老 mediatek `&charger` 忽略项 / `single_batt` USER / `dynamic_mivr_vol` / `max_charger_voltage` / `ambient_temp`→`pid_chg`」见正文 **「老 `&charger`（mediatek,charger）→ 6.12 `tc,charger`」**。含「tran_auto_test→tc_auto_test」：compatible tran,auto_test→tc,auto_test 与节点/phandle 更名。含「extcon_usb」：新分支为准、remote-endpoint 以 SoC 基准 dtsi 解析。
disable-model-invocation: true
funcType: "AI自动化适配"
category: "驱动"
---

# Transsion 充电 DTSI ↔ 驱动对照与新老转换

## 何时使用本 skill

- 用户或任务需要：**结合老内核充电代码** 理解 **老 DTSI / dtsi 里某节点的每个属性在干什么**；
- 随后要在 **新内核（如 `kernel_device_modules-6.12`）** 中找到 **功能相近的配置落点**，并给出 **字段级转换** 或 **[REVIEW] 占位说明**；
- **`tran_otg`（`tran,otg_fun`）** **仅老→新**：**compatible 核对**；老树未配的 **6.12 新属性** 用 **模板默认** 补全；**`otg_boost_*`→`tc_otg_boost_*`** 等改名；产出后 **`[REVIEW]`**（见 **「`tran_otg` 迁移工作流」**）。
- **`smart_charging`（`tran,smart_charging`）**：老侧独立节点 + **`smartchg_min_cur`**；新侧 **无同名 OF 节点**，逻辑在 **`tc_charger`**；**`smartchg_min_cur` 与 `smtchg_curr_min`** 对应关系见 **「`smart_charging`」** 小节。
- **`water_detect`（`transsion, water_detect`）**：**compatible 不变**；**`scheme` 数值** 在 6.12 **因插入 `GPIO_AND_SBU_1_2` 而与 5.10 不完全一致**（**0/1 不变**）；**`bootmode` DT 新侧不读**，见 **「`water_detect`」** 小节。
- **`pid_chg`（`tran,pid_chg_algo` → `tc,pid_chg_algo`）**：**compatible 必改**；新模板常多 **`ambient_temp` / `target_temp_array`**（与 **`power_level` 五档** 对齐）；其余多数字段 **可直拷**，见 **「`pid_chg`」** 小节。
- **`ambient_detect` / `temp_forecast`**：**`transsion,ambient_detect`→`tc,ambient_detect`**、**`transsion,temp_forecast`→`tc,temp_forecast`**；**`ambient_detect` 属性多可整段直拷**；**`temp_forecast`** 注意 **`pa_temp_gap` 新增**、**`machine_gap` 可能废弃** 与 **`orgin_rate` 产品值勿被模板覆盖**，见 **「`ambient_detect` / `temp_forecast`」** 小节。
- **`&pe2` / `&tc30` / `&hvdcp20` / `&pdc`**：overlay 改 **`&tc_pe2` / `&tc_30` / `&tc_hvdcp20` / `&tc_pd`**；**`*_ichg_level_threshold`→`ta_ichg_level_threshold`**；**`vbat_threshold` mV→µV**；**`sc_*`→`chr_volt*`**；**`pdc` 的 `sc_charger_current`→`charger_current_limit`**，见 **「`support_alg` 子节点」** 与 **`transsion-dcp-fastcharge-probe`**。
- **`&extcon_usb`**：**完全按新分支**；**6.12** 用 **Transsion extcon**（`compatible` 以基线为准），**非 6.12** 常见 **`mediatek,extcon-usb`**；**`charger`：`&switch_chg`→`&tc_chgtype`**；**`remote-endpoint`** 从 **芯片平台基准 dtsi** 解析，见 **「`extcon_usb`」** 小节。
- 与 **`tran-projects-config-migrate-dtsi-dws`** 互补：后者偏 **路径/流程/合入纪律**，本 skill 偏 **驱动语义 ↔ DTS 属性 ↔ 新树属性名**。

若仅做文件路径迁移、不含「属性含义与等价项」，可只走 `tran-projects-config-migrate-dtsi-dws`。

**仅生成「`tran_battery` → 6.12 `&charger`」片段与转换表**（含老 PCB 斜率公式、`single_batt_level_*` 19 元布局、tpcb 阶梯拟合步骤）时，由 **`mtk-adapt-upgrade-branch-orchestrator`** 阶段 3/3B **强制 Read** **`transsion-tran-battery-to-tc-charger-dtsi`**；用户即席转换也可单独 @ 该 skill。**不必**为这一块先读本 bridge。

## 必做工作流（四步）

### 1) 锁定老侧证据链

- **DTS 节点**：记录 **compatible**、节点路径（如 `&odm` / `tran_battery`）、**属性名与数值**（含单位：µA、m°C、mV 等）。
- **驱动绑定**：用 **`grep` `of_device_id` / `compatible`** 或 **`of_property_read_*`** 在  
  **`<OLD_KDM>/drivers/power/supply/tran_chg/`**（典型 **`tran_charger.c`**）中找到 **谁解析该节点**。
- **执行路径**：从 **parse_dt / probe** 追到 **限流/状态机**（如 `set_jeita_charging_current`、`change_current_by_pcb_temp`），标出 **哪些属性只存全局、哪些参与每秒决策**。

### 2) 逐项写出「配置项 → 功能」

对每个 DTS 属性给出：

| 维度 | 内容 |
|------|------|
| **语义** | 在充电流程中的作用（JEITA 区、PCB 降流、bootmode、输入/充电流上限等） |
| **单位** | 如 µA、m°C（÷1000 为 ℃）、与 **`thermal_get_*` / gauge 温度** 是否同一标尺 |
| **生效条件** | 例如 `enable_pcb_tml` 为真才走 PCB；SDP 不升某些流等（以老代码为准） |

### 3) 在新内核定位「类似功能」

- **主机侧策略**：`transsion/tc_charger.c`、`tc_basic_charger.c`、`tc_charger_attr.c`（sysfs）、**`tc_desc` 默认表** 与 **设备树属性宏**（如 `TC_DT_VALPROP`、`tc_parse_single_batt_jeita`）。
- **协议/器件**：`tc_pe5`、`tc_chgtype`、`tc_tcpc`、各 `tc_*charger*`；**不要**把「老节点名」当成新 compatible 仍存在于 DT。
- **记清模型差异**：例如老 JEITA 多为 **分区直接写 ichg/icl**；新栈常为 **`single_batt_level_*`（vbat_cc）** + **`tbat_ichg`/`tpcb_ichg`（从 max 减额）** + **充电类型电流** 的合成（见 `tc_basic_charger.c`）。

### 4) 输出转换表与风险

- 给出 **旧属性名 → 新属性名（或「无同名，换机制」）**；
- 标明 **能否 1:1 拷贝数值**（多数 **PCB 折线 → `tpcb_ichg` 阶梯** 需 **拟合**）；
- 标 **`[REVIEW]`**：温区边界、与 **`single_batt` 是否叠扣**、实机电流对齐。

**落地到 dtsi 时**：在片段旁写 **`/* CONVERT: ... */`** 或 **`/* SOURCE: OLD-... */`**，便于 review（与 `tran-projects-config-migrate-dtsi-dws` 的 SOURCE 图例可一致）。

## 已沉淀的典型对照（Tran 5.10 → 6.12 摘要）

以下对应关系在会话中已结合 **`tran_charger.c`（5.10）** 与 **`tc_charger.c` / `tc_basic_charger.c`（6.12）** 核对；迁移细节与 PCB 拟合步骤见 **`tran-projects-config-migrate-dtsi-dws`** 中 **「OLD `tran_battery` → `&charger`」** 小节。

| 老侧（示例） | 新侧落点 | 备注 |
|--------------|----------|------|
| `tran_battery` **`compatible = "tran,chg_fun"`** | **删除**该节点；策略进 **`&charger`（`tc,charger`）** | 新栈 **无** `tran,chg_fun` probe 承接整条策略 |
| **`jeita_*_chg_cur`** | **`&charger` `single_batt_level_*`**（`struct batt_desc` 序列） | 匹配 **`tbat > temp_lo && tbat <= temp_hi`**；**左边界严格大于**，例：含 **-10℃** 时常用 **`temp_lo = -11`** |
| **`jeita_*_input_cur`** | 通常 **不落** 同名温区表 | ICL 由 **`dcp_input_current`、`max_input_current_limit`**、协议栈合成；项目可声明「省略」 |
| **`enable_pcb_tml`、`pcb_temp_*`（m°C）、`pcb_cur_*`** | **`tpcb_temp[]`（℃）+ `tpcb_ichg[]`（µA 减额）** | 新栈 **无 `enable_pcb_tml` 布尔**；**`tpcb_ichg` 全 0** ≈ 不做 PCB 扣流。旧折线需 **按阈值取样拟合** 到阶梯，**非**逐字段粘贴 |
| **`pcb_min_chg_cur`** | **`min_charger_current`** | µA 一致 |
| **`bootmode = <&chosen>`**（仅挂在 `tran_battery`） | **`tc_misc` 等 `bootmode = <&chosen>`**；boot 由 **`tc_get_boot_mode()`** 等 | 删空壳 `tran_battery`，勿留假节点 |
| **`tbat_temp` / `tbat_ichg`** | 与 **`single_batt`** 可能 **叠加** | 主 JEITA 已迁 **`single_batt`** 时，**`tbat_ichg` 常置 0 或弱减额**，避免与 **`vbat_cc` 重复扣同温区（见 migrate skill） |
| **`&charger` `support_alg`** | **必须保留** | **`tc_charger_parse_dt`** 解析字符串列表；合并 fragment 时 **禁止漏删** |
| **`tran_battery_aging` `compatible = "tran,chg_aging"`** | **删除，新树不写等价节点** | 旧驱动为 **`tran_battery_aging.c`**（FG/循环老化表、sysfs/uevent）；**新 KDM `transsion` 无此 compatible**。老化由 **gauge 守护 / `tc_gauge` health、`tc_charger` 的 `aging_*_uisoc` 等**承担。**老→新补充 DTS 时可直接删掉该节点**，无需字段迁移。**`mtk-adapt-upgrade-branch-orchestrator` / inventory 在老 DTS 识别到该节点时直接忽略**，不产出迁移片段、不纳入 3B 字段确认（见 **`transsion-tran-battery-to-tc-charger-dtsi` §0**）。 |
| **`tran_otg` `compatible = "tran,otg_fun"`** | **保留同一 compatible**；驱动 **`tran_chg/tran_otg.c`（5.10）→ `transsion/tc_otg_ctrl.c`（6.12）** | **OF 匹配串未改**；对外 **`tran_get_by_name("tc_otg")`**；**`tc_misc_intf`** 特性表登记 **`tran,otg_fun`**。**老→新**：**先核对 compatible**；老树缺项用 **模板默认** 补 **6.12 全量属性**；**`otg_boost_*`→`tc_otg_boost_*`**；见 **「`tran_otg` 迁移工作流」** 与 **`[REVIEW]`**。 |
| **`tran_auto_test` `compatible = "tran,auto_test"`** | 节点 **`tc_auto_test`**；**`compatible = "tc,auto_test"`** | **OF 串变更**（5.10 **`tran_auto_test.c`**：`"tran,auto_test"` → 6.12 **`tc_auto_test.c`**：`"tc,auto_test"`）。**节点名**由 **`tran_auto_test`** 改为 **`tc_auto_test`**。板级 **`&tran_auto_test` / label** 须同步为 **`&tc_auto_test`**，**`[REVIEW]`** 全树无残留旧名。 |
| **`smart_charging` `compatible = "tran,smart_charging"`** | **删除独立节点**；功能在 **`tc_charger`（`tc,charger`）** 内 + **sysfs** | **`smartchg_min_cur`（µA）** 对应 **`struct tc_desc` 的 `smtchg_curr_min`**（默认 **500000** µA）。**当前 6.12 `tc_charger.c` 的 `tc_dtprops_u32` 未注册该属性**，一般 **不写进 `&charger` dtsi**；与老树 **500000** 一致时可依赖默认，否则 **`[REVIEW]`**（打补丁加 DT 或 init 写 sysfs）。见 **「`smart_charging`」** 小节。 |
| **`water_detect` `compatible = "transsion, water_detect"`**（**逗号后空格须与 OF 表一致**） | **保留独立节点**；**`tran_water_detect.c`（5.10）→ `tc_water_detect.c`（6.12）`** | **`scheme` 数值与老枚举不完全兼容**（6.12 插入 **`GPIO_AND_SBU_1_2=2`**，后续枚举顺延）；**`scheme=0/1` 不变**；**`bootmode`** 在 6.12 probe **不再读 DT**，改为 **`tc_get_boot_mode()`**；**`polling_interval`、`gpio_*` 等** 仍由 **`water_detect_parse_dt`** 解析。见 **「`water_detect`」** 小节。 |
| **`pid_chg` `compatible = "tran,pid_chg_algo"`** | **保留 `pid_chg:` 节点**；**`compatible` → `"tc,pid_chg_algo"`**；其余多数 **属性名与数值可直拷** | 新 KDM 模板常 **多出** **`ambient_temp`**、**`target_temp_array`**（与 **`power_level` 五档** 对齐）；老树无则 **从新树参考 `tc_charger.dtsi` 抄默认或 BA 调参**，**`[REVIEW]`**。若老 **`mediatek,charger` 的 `&charger`** 上曾挂此二属性，**一并摘到 `pid_chg`**，**勿**留在新 **`&charger`**。见 **「`pid_chg`」** 小节与 **「老 `&charger`（mediatek,charger）」** 第 5 条。 |
| **`ambient_detect` `compatible = "transsion,ambient_detect"`** | **保留节点**；**`compatible` → `"tc,ambient_detect"`** | 与 **lj9 `tc_charger.dtsi` 模板**对照：**属性集合与示例数值可与老树一致直拷**（**`qmax`～`power_delta_temp`**）。见 **「`ambient_detect` / `temp_forecast`」** 小节。 |
| **`temp_forecast` `compatible = "transsion,temp_forecast"`** | **保留节点**；**`compatible` → `"tc,temp_forecast"`** | 新模板常 **增 `pa_temp_gap`**、**去掉 `machine_gap`**（以 **`tc_temp_forecast*.c` parse_dt** 为准）；**`orgin_rate` 拼写保留**（历史笔误）。见同小节。 |
| 板级 **`&pe2` / `&tc30` / `&hvdcp20` / `&pdc`** overlay | fragment 目标改为 **`&tc_pe2` / `&tc_30` / `&tc_hvdcp20` / `&tc_pd`**（节点在 **`tc_charger.dtsi`**） | **`*_ichg_level_threshold`→`ta_ichg_level_threshold`**；**`vbat_threshold` 老 mV 整数 → 新 µV（×1000）**；**`sc_*`→`chr_volt*` 分档向量**；**`pdc`：`sc_charger_current`→`charger_current_limit`** 等；**线缆阻抗 / 双串 DCS** 未必仍在同节点 — **`[REVIEW]`**。见 **「`support_alg` 子节点」**、**`transsion-dcp-fastcharge-probe`**。 |
| **`&extcon_usb`**（USB 角色 / extcon） | **以新分支 SoC 基准 dtsi + 新 Tran `tc_charger.dtsi` fragment 为准**；**勿**用老树 **`mediatek,extcon-usb`** 整块覆盖基线 | **6.12 新栈**：extcon 走 **Transsion 绑定**（**`compatible` 以 6.12 平台基线 + 驱动 `of_match` 为准**，与 **`mediatek,extcon-usb`** 区分）；**其它内核版本**仍可能为 **`mediatek,extcon-usb`**。**`charger`**：**`&switch_chg`→`&tc_chgtype`**（见 lj9 模板）。**`remote-endpoint`**：**必须从芯片平台基准 dtsi**（SoC + Type-C/USB 图）**解析**对端 phandle。见 **「`extcon_usb`」** 小节。 |

### 老 `&charger`（`compatible = "mediatek,charger"`）专有项 → 6.12 **`&charger`（`tc,charger`）**

适用于 **5.10 `tran_charger.dtsi` / 板级 overlay** 中与 **`mediatek,charger`** 绑定的 **旧属性名**；新 KDM **`tc_charger.c` 不再解析** 的项 **柱 2 直接忽略**（**不写进**新 `tc_charger.dtsi`、**不**做数值迁移）；须迁移的项按下列 **闸门** 处理。

#### 1) 新分支 **不解析** — 适配时 **一律忽略**（勿写入新 DTS）

下列属性 **6.12 `tc,charger` 侧无等价 OF 解析**（以目标树 **`Read tc_charger.c` / `tc_dtprops_*`** 为准），老→新 **删除即可**，可在 CONVERT 注释中标 **`/* DROP: not parsed on tc,charger */`**：

- **`algorithm_name`**
- **`power_path_support`**
- **`disable_pd_dual`**
- **`charger_configuration`**
- **`multi_battery_cv`** 与 **`battery_cv`**（多电芯 CV 头 + 向量）
- **`usb_charger_current_suspend` / `usb_charger_current_unconfigured` / `usb_charger_current_configured`**
- **`charging_host_charger_current`**
- **`apple_1_0a_charger_current` / `apple_2_1a_charger_current`**
- **`ta_ac_charger_current`**
- **`enable_min_charge_temp`**
- **`min_charge_temp_plus_x_degree`**
- **`max_charge_temp_minus_x_degree`**

#### 2) 语义已并入 **`single_batt_level` / `single_batt_level_*`** — **本 skill 不写转换公式**

下列老属性（含 **SW JEITA 温度门限整簇**、**FFC/非 FFC EOC 相关**、**`dv2_ffc_gera_*`**）在新栈由 **`single_batt_level*`**（及驱动内 **`tc_parse_single_batt_jeita` / `tc_chg_update_single_batt_jeita`**）承载：

- **`temp_t4_thres`、`temp_t4_thres_minus_x_degree`、`temp_t3_thres`、`temp_t3_thres_minus_x_degree`、`temp_t2_thres`、`temp_t2_thres_plus_x_degree`、`temp_t1_thres`、`temp_t1_thres_plus_x_degree`、`temp_t0_thres`、`temp_t0_thres_plus_x_degree`、`temp_neg_t1_thres`、`temp_neg_t1_thres_plus_x_degree`、`temp_neg_10_thres`**
- **`ffc_battery_cv`、`ffc_eoc`、`non_ffc_eoc`**
- **`dv2_ffc_gera_cv`、`dv2_ffc_gera_cycle`**

**柱 2 动作**：在新 **`tc_charger.dtsi`** 的 **`&charger`** 中 **预留/补全 `single_batt_level` 与 `single_batt_level_*`**，**具体 19 元布局与数值由用户（或电池表流程）填写**，并标注 **`/* USER: single_batt — 由电池规格 / 电池表生成，勿从老 mediatek &charger 机械抄数 */`**。**算法级如何从老表填进 `single_batt`**：执行 **`Read` `transsion-tran-battery-to-tc-charger-dtsi`** 与 **`mtk-adapt-template-basic-charging-capability`** 中 **`single_batt_level*` 格式规则**；**本 bridge 不展开推导步骤**。

#### 3) **须转写** — **`dynamic_mivr_vol`**

- **`min_charger_voltage_1`、`min_charger_voltage_2`、`max_dmivr_charger_current`** → 新 **`&charger`** 的 **`dynamic_mivr_vol`**（及若驱动仍要求配套 **`min_charger_voltage`** 等，一并核对）。
- **维数、单位（µV）、元顺序** 以 **`tc_charger.c` / `tc_basic_charger.c`** 对 **dynamic MIVR** 的 **`of_property_read_u32_array`** 语义为准；柱 2 **必须 `Read` 新驱动** 后再填，**禁止**无依据假定三老值与参考模板四元组一一对应。

#### 4) **同名直拷**

- **`max_charger_voltage`**：新分支 **`&charger` 仍解析** 时 **可同步**老树数值（单位须与新驱动一致，常见 **µV**）；合入前 **`Read tc_charger.c`** 确认属性名未变。

#### 5) **迁节点** — **`ambient_temp` / `target_temp_array`**

- 若老树把 **`ambient_temp`、`target_temp_array`** 挂在 **`mediatek,charger` 的 `&charger`** 上：新树 **须写入 `&odm` 下 `pid_chg`（`tc,pid_chg_algo`）**，与 **`power_level` 五档** 对齐；**勿**继续放在新 **`&charger`** 节点上。详见上表 **`pid_chg`** 行与 **「`pid_chg`」** 正文。

### `smart_charging`（`tran,smart_charging`）老 → 新

典型老树：

```dts
smart_charging {
	compatible = "tran,smart_charging";
	smartchg_min_cur = <500000>;
	status = "okay";
};
```

**老侧（5.10）**

- **驱动**：`drivers/power/supply/smart_charging.c`，**`compatible = "tran,smart_charging"`**，注册 **`tran_device`**，**`alias_name = "smart_charging"`**（`SMART_CHARGING_NAME`）。
- **DTS**：**`smartchg_min_cur`** 读入 **`smartchg_device.smartchg_min_cur`**（µA）；缺省为 **`SMTCHG_MIN_CURRENT`（0）**（见 `smart_charging.h`）。可选 **`smartchg_name`** 字符串。
- **被谁用**：`tran_charger.c` 等 **`tran_get_by_name("smart_charging")`**，取 **`TRAN_PROP_GET_CHARGER_CURRENT`** 等与 **`smartchg_min_cur` / bypass 状态** 合成限流。

**新侧（6.12）**

- **无**独立 **`tran,smart_charging`** 平台节点；智能充/旁路相关状态在 **`tc_charger.c`** 的 **`struct smart_chg_data smtchg_data`**，由 **`tc_smart_charger_hdlr`** 与 **`wait_protocol_array[SMART_CHG]`** 更新。
- **最低电流语义**：在 **smart 模式且 `smartchg_energy == SMTCHG_ENERGY_MIN`** 时，对 **`total_ichg_vote`** 投 **`SMTCHG_VOTER`**，值为 **`desc->smtchg_curr_min`**（µA）。
- **`smtchg_curr_min` 来源**：**`tc_desc` 默认 `500000`**（与示例 **`smartchg_min_cur = <500000>`** 一致）；**运行时** 可由 **`tc_charger_attr.c`** 下 **`odm:smart_charging/smart_mincur`** sysfs 改写 **`desc->smtchg_curr_min`**。
- **与 DTS**：在已检索的 **`tc_charger.c`** 中，**`smtchg_curr_min` 未出现在 `tc_dtprops_u32[]` 等 DT 解析表**，即 **合入新树时通常不在 `&charger { }` 里增加 `smartchg_min_cur` 或 `smtchg_curr_min` 属性**（除非你们本地已打补丁把该字段接入 `TC_DT_VALPROP`）。若老树为 **非 500000** 且必须固化进镜像：**`[REVIEW]`** — 补丁扩展 DT、或 init 写 **`smart_mincur`**、或与 BA 对齐策略。

**迁移动作（老 → 新）**

1. **删除** **`smart_charging { compatible = "tran,smart_charging"; ... }`** 整块。
2. **`smartchg_min_cur = <500000>`**：与 **`default_info.smtchg_curr_min`** 默认一致时，**可不写任何新属性**；在 CONVERT 注释中注明 **「沿用 tc_charger 默认 smtchg_curr_min」**。
3. **`smartchg_min_cur` ≠ 500000** 或需可配置：**`[REVIEW]`** 选补丁 / sysfs / 产品策略。
4. 若有 **`smartchg_name`**：新栈仍通过 **`tran_get_by_name("smart_charging")` 类路径已移除**；以 **`tc_charger`** 为准，无需同名 DTS 字符串。

### `water_detect`（`transsion, water_detect`）老 → 新

典型老树（与常见注释一致）：

```dts
water_detect: water_detect {
	status = "okay";
	compatible = "transsion, water_detect";
	bootmode = <&chosen>;
	polling_interval = <5>;
	scheme = <1>; /* 0: subPMIC/USB-ID 路径; 1: 纯 GPIO X/Y 状态检测 */
	gpio_x = <&pio 21 0x00>;
	gpio_y = <&pio 62 0x00>;
};
```

#### `compatible`（必须逐字符一致）

- 5.10 / 6.12 的 **`of_device_id`** 均为 **`"transsion, water_detect"`**（**逗号后有一个空格**）。DTS 若写成 **`transsion,water_detect`**（无空格）将 **不匹配**。**`[REVIEW]`** 合入前在板级 dtsi 中核对字符串 **与源码完全一致**。

#### `scheme` 数值映射（**重点**）

6.12 在枚举中 **于 `SCHEME_GPIO` 之后插入了 `SCHEME_GPIO_AND_SBU_1_2 = 2`**，导致 **`SCHEME_USB_SWITCH` 及之后取值整体 +1（或更多）**，**不可**假设「老 `scheme` 数字 = 新 `scheme` 数字」。

| 老 5.10 `scheme` 数值 | 老侧符号（`tran_water_detect.c`） | 新 6.12 `scheme` 数值 | 新侧符号（`tc_water_detect.h`） |
|----------------------|-----------------------------------|----------------------|----------------------------------|
| **0** | `SCHEME_SUBPMIC` | **0** | `SCHEME_SUBPMIC` |
| **1** | `SCHEME_GPIO`（GPIO X/Y 电平检测） | **1** | `SCHEME_GPIO` |
| **2** | `SCHEME_USB_SWITCH` | **3** | `SCHEME_USB_SWITCH` |
| **3** | `SCHEME_USB_ID_AND_GPIO` | **4** | `SCHEME_USB_ID_AND_GPIO` |
| **4** | `SCHEME_SBU_AND_GPIO` | **2** | `SCHEME_GPIO_AND_SBU_1_2` |

- 你给出的 **`scheme = <1>`**（注释为 GPIO 状态检测）在 **两侧均为 `SCHEME_GPIO`** → **数值保持 1，无需修改**。
- 若老树曾为 **`scheme = <4>`（SBU+GPIO）**，迁到 6.12 应写 **`<2>`**（并补齐 **`gpio_z` / `gpio_w` / `gpio_sbu2_micgnd`** 等 **`tc_water_detect_parse_dt`** 要求的脚，以新驱动 `water_detect_parse_dt` 分支为准），**`[REVIEW]`** 实机进水检测。
- 新树 **新增** **`scheme = <5>`**（`SCHEME_USB_ID_AND_GPIO_AND_SBU_1_2`）在老内核 **无同名枚举**，老→新迁移 **不要**凭空写 5，除非产品定义走该组合路径。

#### `bootmode`

- **5.10**：`water_detect_probe` 使用 **`of_parse_phandle(..., "bootmode", 0)`** 读 **`chosen`**，再取 **`atag,boot`** 得到 **`boot_mode`**，用于 **KPOC / 工厂等** 分支（`wd_kpoc`、`wd_factory`）。
- **6.12**：`tc_water_detect.c` 的 **`water_detect_probe`** 改为 **`boot_mode = tc_get_boot_mode();`**，**不再解析 DT 属性 `bootmode`**。
- **迁移动作**：新树节点上的 **`bootmode = <&chosen>;` 可删除**（避免误以为仍生效）；确保 **`tc_misc` / `tc_get_boot_mode()`** 路径与产品 bootmode 一致，**`[REVIEW]`**。

#### 其它 DTS 属性

- **`polling_interval`**：两侧 **`water_detect_parse_dt`** 均读取；缺省 **5**（秒，`ktime_set(info->polling_interval, 0)`）。
- **`gpio_x` / `gpio_y`**（及方案所需的 **`gpio_z` / `gpio_w` / `gpio_sbu2_micgnd`**）：仍为 **`of_get_named_gpio`**；**pio 引用**随平台 dtsi 迁移即可。
- **节点 label**：仍可 **`water_detect:`**；驱动 **`alias_name` 仍为 `"water_detect"`**（`tran_get_by_name("water_detect")`）。若项目规范要求 **`tc_water_detect`** 标签，仅影响 phandle/可读性，**与 compatible 无关**，**`[REVIEW]`** 全树引用。

#### 6.12 probe 依赖（合入时注意 defer）

- 新 **`water_detect_probe`** 会取 **`tcpc_dev_get_by_name("type_c_port0")`**、**`tran_get_by_name("tc_charger")`** 等，失败可 **`-EPROBE_DEFER`**；板级 **init 顺序 / 依赖** 与老树可能不同，**`[REVIEW]`** 首次开机 log。

### `pid_chg`（PID 充电温控 / 亮屏功耗模型）老 → 新

典型老树（`&odm` 下，与多项目 **`tran_charger.dtsi`** 一致）：

```dts
pid_chg: pid_chg {
	compatible = "tran,pid_chg_algo";
	pid_array = <1000 100 10000>;   /* KP KI KD */
	polling_interval = <10000>;
	power_level = <800 1600 2400 3200 4000>;
	power_delta_temp = <0 100 200 300 300>;
	power_update_time = <300>;
	power_meas_current = <400000>;
	target_temp_gap = <50>;
	steady_cycle = <2>;
	max_steady_target_delta_temp = <50>;
	max_steady_delta_temp = <30>;
	normal_steady_delta_temp = <20>;
	max_unsteady_cnt = <2>;
	max_target_temp = <4400>;
	/* support_ibus_measure; */
	ibus_measure_power_update_time = <60>;
	delta_current_max = <500000>;
};
```

#### 与 `tran_auto_test` 类比的 **唯一硬变更**：`compatible`

- **5.10**：**`"tran,pid_chg_algo"`**。
- **新 KDM（如 `kernel_device_modules-6.1` / `6.12` 工程模板）**：**`"tc,pid_chg_algo"`**（见仓库 **`tran_projects/lj9/.../kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/tc_charger.dtsi`** 中 **`pid_chg`** 节点）。
- **节点名 `pid_chg:`** 在参考模板中 **未改为 `tc_pid_chg`**，板级 **`&pid_chg`** 一般 **可保留**；若全项目统一 **`tc_*` 前缀** 再改 label，须 **`[REVIEW]`** 全树 phandle。

#### 老树已有、新树模板仍保留的属性（**键名通常不变，数值可直拷**）

| 属性 | 常见单位 / 语义（据 DTS 注释与命名） |
|------|--------------------------------------|
| **`pid_array`** | 三个 **s32**：**KP、KI、KD**（离散实现里的增益；内部定标以驱动为准）。 |
| **`polling_interval`** | 控制周期下限（模板注释 *minimum time for each cycle*；单位以 **`tc_pid_chg*.c` 的 `parse_dt`** 为准，常见为 **ms**）。 |
| **`power_level`** | 与 **`power_delta_temp`** **等长**（多为 **5** 档）：亮屏平均功耗分档（模板注释 *mW 量级* 的功耗档，具体解释以驱动为准）。 |
| **`power_delta_temp`** | 与 **`power_level`** 逐档对应的 **温差 / 补偿量**（与 **`max_target_temp` 等** 同族，多为 **0.01℃** 即 **m°C** 整数，**`[REVIEW]`** 驱动常量）。 |
| **`power_update_time`** | 平均功耗统计刷新周期（**秒**，模板注释）。 |
| **`power_meas_current`** | 测平均功耗时固定的 **ibus**（**µA**）。 |
| **`target_temp_gap`** | PID 目标与采样温差相关门限（**m°C** 量级）。 |
| **`steady_cycle` / `max_steady_*` / `normal_steady_delta_temp` / `max_unsteady_cnt`** | **稳态判定**：连续满足几拍、目标偏差与温升变化上/下限、非稳态计数容忍等（精确判据以驱动为准）。 |
| **`max_target_temp`** | 目标温度上限（例 **4400** → 常表示 **44.00℃**，**m°C**）。 |
| **`support_ibus_measure`** | **bool**（可选）：走 **ibus 估算功率** 的分支；老树常注释掉 = 默认关。 |
| **`ibus_measure_power_update_time`** | **ibus 测功耗时** 的刷新周期（**秒**）。 |
| **`delta_current_max`** | 单次调节 **充电电流变化上限**（**µA**），限制 PID 输出跳变。 |

#### 新树模板 **新增**、老树常 **没有** 的两项（**合入必对**）

参考 **`tc_charger.dtsi`**（lj9 6.1 模板）在 **`pid_array` 与 `power_level` 之间**插入：

```dts
ambient_temp = <250 250 250 250 350>;
target_temp_array = <3900 3900 3900 3900 4300>;
```

- **`ambient_temp`**、**`target_temp_array`**：各 **5** 个 **s32**，与 **`power_level` 五档** 一一对应；语义为 **环境温度带 / 各档目标温度**（**m°C** 类整数，与 **`max_target_temp`** 同量级），用于新算法在 **功耗分档 + 环温** 下选目标或修正。**老树无此二属性时，不可留空**：从 **目标新平台已量产 `tc_charger.dtsi`** 抄一对默认值，再按产品热设计 **`[REVIEW]`** 调参。

#### 迁移动作小结

1. **`compatible`**：**`tran,pid_chg_algo`** → **`tc,pid_chg_algo`**。
2. **其余键值**：与参考 **`tc_charger.dtsi`** **diff**；多数可 **原样迁移**。
3. **补** **`ambient_temp`**、**`target_temp_array`**（或确认驱动对缺省有安全 fallback——**以 `tc_pid_chg*.c` 的 `parse_dt` 为准**，无则必须写）。
4. **`[REVIEW]`**：合入后 **`rg "tran,pid_chg_algo"`** 板级应为零；首发热插拔 + 亮屏游戏场景看 **温升与限流是否过激/过钝**。

### `ambient_detect` / `temp_forecast`（`transsion,*` → `tc,*`）老 → 新

以下对照以仓库 **老树 `tran_projects/lj6/.../tran_charger.dtsi`** 与 **新树 `tran_projects/lj9/.../kernel_device_modules-6.1/.../tc_charger.dtsi`** 中 **`&odm` 下同名节点**为准（不同项目数值可能不同，**键名迁移规则一致**）。

#### `ambient_detect`

| 侧 | `compatible` |
|----|----------------|
| 5.10 典型 | **`transsion,ambient_detect`** |
| 新 KDM 模板 | **`tc,ambient_detect`** |

- **属性**：在你给出的示例与 **lj9 模板**之间，**`qmax`～`power_delta_temp` 键名与顺序一致**，数值可 **整段直拷** 后再按新产品微调。
- **语义速查**（单位以驱动为准，常见为 **秒 / mAh / mW 或 0.1℃ 整数** 等 — 合入前 **`[REVIEW]`** 对 `tc_ambient_detect*.c`）：**`qmax`** 电芯容量相关；**`polling_interval`** 轮询周期；**`ambient_max_power`** 与 **功耗判定**；**`ambient_max/min_temp`** 环温可用范围；**`min_detection_duration`** 最短有效检测时长；**`ambient_low_power_update_time` / `ambient_charging_time` / `ambient_cooling_time`** 低功耗与充/放热过程时间窗；**`ambient_max_update_time` / `ambient_max_temp_rate` / `ambient_max_diff_pcb_temp`** 更新节奏与温升/PCB 温差约束；**`min_update_soc_diff` / `plug_update_soc_diff`** 与 **SOC 变化、插拔** 触发刷新阈值；**`power_level` + `power_delta_temp`** 与 **`pid_chg`** 类似为 **分档功耗—温差** 表（**长度须一致**）。

#### `temp_forecast`

| 侧 | `compatible` |
|----|----------------|
| 5.10 典型 | **`transsion,temp_forecast`** |
| 新 KDM 模板 | **`tc,temp_forecast`** |

**老树（lj6）示例**：

```dts
temp_forecast: temp_forecast {
	compatible = "transsion,temp_forecast";
	orgin_rate = <85>;
	max_temp_diff = <150>;
	max_comp_temp = <30>;
	per_rate_time = <5>;
	machine_gap = <0>;
};
```

**新树（lj9）模板**：

```dts
temp_forecast: temp_forecast {
	compatible = "tc,temp_forecast";
	orgin_rate = <70>;
	max_temp_diff = <150>;
	max_comp_temp = <30>;
	pa_temp_gap = <500>;
	per_rate_time = <5>;
};
```

- **`orgin_rate`**：属性名在两侧均为 **`orgin_rate`**（**非** `origin_rate`），属 **历史拼写**；迁树时 **保留老树数值**（例 **85**），**不要**被参考模板里的 **70** 默默覆盖，除非 BA 明确要求。
- **`machine_gap`**：老树有、**lj9 模板无** — 可能已被算法废弃或并入其它项；**`[REVIEW]`** **`tc_temp_forecast*.c`**：若驱动 **仍解析**则保留；若 **无 `of_property_read`** 对应字段则删除并在 CONVERT 注释说明依据。
- **`pa_temp_gap`**：新模板 **新增**；老树无则 **须补**。无单独量产基准或 BA 指定时，**项目默认写 `<500>`**（与 **`mtk-adapt-template-basic-charging-capability`**）；若有目标平台已量产 **`tc_charger.dtsi`** 则从基准。**`[REVIEW]`** **PA/壳温预测** 相关 log。

#### 迁移动作小结

1. **`ambient_detect`**：改 **`compatible`**；其余 **整段拷贝** → **`[REVIEW]`** 单位与环温策略。
2. **`temp_forecast`**：改 **`compatible`**；**保留 `orgin_rate` 产品值**；**补 `pa_temp_gap`**；**`machine_gap`** 按驱动是否仍解析决定去留。
3. **`rg`**：**`transsion,ambient_detect`**、**`transsion,temp_forecast`** 在板级 dtsi 中应为 **零残留**（除非声明双栈并存）。

### `support_alg` 子节点：`&pe2` / `&tc30` / `&hvdcp20` / `&pdc` 板级 overlay → `tc_charger.dtsi` 内 `tc_*`

老分支常在 **板级 dtsi** 用 **`&pe2` … `&pdc`** 覆盖 **Tran 快充算法子节点**（与 **`&charger` 的 `support_alg`** 字符串联动，见 **`transsion-dcp-fastcharge-probe`**）。新 KDM 将同类节点 **收进 `tc_charger.dtsi`**（例：**`tran_projects/lj9/.../kernel_device_modules-6.1/.../tc_charger.dtsi`**），**label 与 fragment 目标名变化**，且 **若干属性从「单档」改为「按 VBUS 分档的向量」**。

#### 1) Fragment 目标（**易错：`tc30` → `tc_30`**）

| 老树 overlay | 新树 overlay（须与 **`tc_charger.dtsi`** 中 label 一致） |
|--------------|----------------------------------------------------------|
| **`&pe2`** | **`&tc_pe2`**（节点 **`tc_pe2: tc_pe2`**，`compatible = "transsion,pe20_charger"`） |
| **`&tc30`** | **`&tc_30`**（节点 **`tc_30: tc_30`**，中间为 **下划线**） |
| **`&hvdcp20`** | **`&tc_hvdcp20`** |
| **`&pdc`** | **`&tc_pd`** |

**`compatible`（子节点）**：lj9 模板上 **PE20 / TC30 / HVDCP20 / PD** 仍为 **`transsion,pe20_charger` / `transsion,tc30_charger` / `transsion,hvdcp20_charger` / `transsion,pd_charger`** — **与老树 OF 串一致**；迁移重点是 **phandle 目标名** 与 **属性表形态**，不是改这四个 compatible。

#### 2) 通用：TA 电流门限与 SOC

| 老树属性 | 新树属性 | 说明 |
|----------|----------|------|
| **`pe20_ichg_level_threshold`** | **`ta_ichg_level_threshold`** | 单位均为 **µA**；语义：TA 侧/协议某路径的 **ichg 档阈**（以 **`tc_pe20*.c` parse_dt** 为准）。 |
| **`tc30_ichg_level_threshold`** | **`ta_ichg_level_threshold`** | 同上（**TC30** 子节点内）。 |
| **`hvdcp20_ichg_level_threshold`** | **`ta_ichg_level_threshold`** | 同上。 |
| **`ta_start_battery_soc`** | （lj9 模板 **常省略**） | 多为 **0** 或改由 **`tc_charger` / 算法默认**；若老树为非 0 且产品依赖：**`[REVIEW]`** 新驱动是否仍从 DT 读同名或等价项。 |
| **`ta_stop_battery_soc`** | **`ta_stop_battery_soc`**（PE20、TC30、HVDCP20） | 单位 **SOC 百分比**；键名不变。 |
| **`pd_stop_battery_soc`**（若老 **`&pdc`** 有写） | **`pd_stop_battery_soc`**（**`tc_pd`**） | 与上类似；lj9 **`tc_pd`** 示例为 **90**；老树 x6880 曾有 **100** — **迁树保留产品值**。 |

#### 3) **`vbat_threshold`（单位陷阱）**

| 老树写法 | 新树写法（lj9 模板） | 规则 |
|----------|---------------------|------|
| **`vbat_threshold = <4350>;`**（多为 **mV** 整数） | **`vbat_threshold = <4350000>;`** | **×1000 → µV**（与 **`min_charger_voltage`** 等同族 **µV**）。**禁止**把 **`<4350>`** 原样贴进新节点。 |

#### 4) PE20 / TC30 / HVDCP20：**`min_charger_voltage` + `sc_*` → `chr_volt*` 向量**

老树用 **单组** **`min_charger_voltage`**、**`sc_input_current`**、**`sc_charger_current`** 描述 **当前策略下** 的 MIVR 与单charger电流；新树用 **与 VBUS 档位对齐的数组**（长度须与 **`chr_volt` 元素对数**一致，见模板）：

- **`chr_volt`**：**µV**，成对或成序列出各档 **VBUS/充电电压轨**（PE20 常见 **5V / 9V**；TC30 常见 **5V / 7.5V** 多档；HVDCP20 常见 **5V / 9V** 等 — **以模板与硬件为准**）。
- **`chr_volt_mivr`**：与各档对齐的 **MIVR（µV）**；老树 **`min_charger_voltage = <4600000>`** 通常映射到 **各档下限里至少一档为 4.6V**（例 lj9 **`4600000 8000000`** 对 5V/9V）。
- **`chr_volt_input_cur`**：**每档 AICR/输入限流（µA）** ← 承接老树 **`sc_input_current`**（若多档相同则重复写；**TC30** 老树 **`sc_input_current = <2400000>`** 对应模板里 **2400000** 出现在 **7.5V 相关档**）。
- **`chr_volt_chg_cur`**：**每档充电电流（µA）** ← 承接 **`sc_charger_current`**（lj9 模板示例 **3600000**；你贴 **3000000** 则按产品写入对应槽位）。

**新增/模板常见、老树未必有：**

- **`tc_pe2`**：lj9 无 **`recover_*`** 时可能不需要；**`tc_hvdcp20`** 可有 **`recover_9v_gap`**；**`tc_30`** 可有 **`recover_7v5_gap`**（**µV** 量级间隔，防回退抖动 — 以 parse_dt 为准）。

#### 5) PE20 老树专有：**线缆阻抗**、**双串 DCS**

| 老树属性 | 新树（lj9 **`tc_pe2` 片段）** | 说明 |
|----------|------------------------------|------|
| **`cable_imp_threshold`**、**`vbat_cable_imp_threshold`** | **未出现在 `tc_pe2` 同段** | 可能迁至 **`tc_chg_type_det` / `&charger` / 其它 tchg 节点** 或改 **算法内默认**。**`[REVIEW]`** **`rg cable_imp`** 于 **`drivers/power/supply/transsion`**。 |
| **`dcs_input_current`**、**`dcs_chg1_charger_current`**、**`dcs_chg2_charger_current`**、**`dual_polling_ieoc`**、**`slave_mivr_diff`** | **同段未出现** | **双充电串** 路径可能由 **`tc_charger` + charge pump 描述** 或 **另一 dtsi** 承接；**不可**假设删除后行为不变。**`[REVIEW]`** 硬件是否为双charger及新栈等价配置。 |

#### 6) **`&pdc` → `&tc_pd`**

| 老树属性 | 新树属性（lj9 **`tc_pd`**） | 说明 |
|----------|------------------------------|------|
| **`pd_vbus_upper_bound`** | **`pd_vbus_upper_bound`** | **µV**；你示例 **9M**；lj9 模板 **10M** — **保留产品上限**。 |
| **`min_charger_voltage`** | **`min_charger_voltage`** | **µV**；一致。 |
| **`sc_input_current`** | （无同名） | 固定 PD 路径下 **输入限流** 可能并入 **`tc_charger` 的 ICL vote** 或 **`chr_volt_input_cur` 类结构**；lj9 **`tc_pd`** 片段未单列 — **`[REVIEW]`**。 |
| **`sc_charger_current`** | **`charger_current_limit`** | **µA**；lj9 示例 **3600000**；你写 **3000000** 则按产品写入。 |
| **`ibus_err`** | **未在 lj9 `tc_pd` 同段** | **`[REVIEW]`** 是否迁至 **`&charger`** 或 **`tc_pe50` / `tc_gauge` 链路**。 |
| **`vsys_watt`** | **未在 lj9 `tc_pd` 同段** | 同上。 |
| **`ta_ichg_level_threshold`**（老树 **`&pdc`** 未必有） | **`ta_ichg_level_threshold`** | lj9 模板 **有**；与 **TA 电流档** 一致。 |
| — | **`pd_vbus_low_bound`** | lj9 模板 **新增**（例 **5M**）；老树无则 **从模板或量产项目抄**，**`[REVIEW]`** PPS/低压 PD 窗口。 |

#### 7) 迁移动作小结

1. 板级 **search-replace**：**`&pe2`→`&tc_pe2`**，**`&tc30`→`&tc_30`**，**`&hvdcp20`→`&tc_hvdcp20`**，**`&pdc`→`&tc_pd`**。
2. 重排 **PE20/TC30/HVDCP20** 属性：按 **`chr_volt` 档位数** 填 **`chr_volt_mivr` / `chr_volt_input_cur` / `chr_volt_chg_cur`**，并把 **`vbat_threshold` 改为 µV**。
3. **`tc_pd`**：**`sc_charger_current`→`charger_current_limit`**；补 **`pd_vbus_low_bound`** 等模板项；核对 **`pd_stop_battery_soc`**。
4. **双串 / 线缆阻抗 / ibus_err / vsys_watt**：**`[REVIEW]`** 全树与 **`transsion-dcp-fastcharge-probe`** 中 **`support_alg` 与器件拓扑** 是否仍覆盖。

### `extcon_usb`（`&extcon_usb`）老 → 新：**完全跟新分支**

#### 原则

- **老→新合入时：`&extcon_usb` 以「新分支 SoC 平台基准 dtsi + 新 Tran 充电 fragment」为唯一信源**，**不要**把老树下面这种 **整块**当成权威再覆盖新基线：

```dts
&extcon_usb {
	compatible = "mediatek,extcon-usb";
	status = "okay";
	charger = <&switch_chg>;
	bootmode = <&chosen>;
};
```

- **理由**：**6.12 / 新 Tran 栈**上 extcon 的 **驱动绑定、图连接、`charger` 指向** 已与 **`mediatek,extcon-usb` + `&switch_chg`** 时代分叉；强行保留老树 **易与 SoC 基线重复定义或断图**。

#### `compatible`：6.12（Transsion extcon）vs 其它内核（MediaTek extcon）

| 场景 | 典型 `compatible` | 说明 |
|------|-------------------|------|
| **6.12 新 Tran 充电/USB 栈** | **Transsion 侧 extcon**（**具体字符串以芯片平台基准 dtsi 与 `drivers/.../extcon*.c` 的 `of_device_id` 为准**） | 与老树 **`mediatek,extcon-usb`** **不是**同一 OF 串；**禁止**在未核对基线的情况下写回 **`mediatek,extcon-usb`**。 |
| **其它内核 / 未切 Tran extcon 的树** | **`mediatek,extcon-usb`** | 仍走 MTK 原厂 extcon 绑定；与本节 **6.12** 分支 **分流**。 |

**`[REVIEW]`**：在目标 **`kernel_device_modules-6.12`**（或你们等价 KDM）里对 **`extcon_usb` 节点**执行 **`rg "extcon_usb:|compatible.*extcon" arch/arm64/boot/dts`**，以 **SoC 根 dtsi / pmic / ssusb** 中的 **定义节**为准。

#### `charger` phandle

- **老树**：**`charger = <&switch_chg>;`**
- **新 Tran 模板（lj9 `tc_charger.dtsi` fragment）**：仅保留 **`charger = <&tc_chgtype>;`**（与 **`&mtk_gauge` / `&mt6375_typec` 等** 对齐到同一 **chgtype** 入口）。

```419:421:tran_projects/lj9/lj9_h972_e1/lj9/kernel/kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/tc_charger.dtsi
&extcon_usb {
	charger = <&tc_chgtype>;
};
```

- **`bootmode`**：lj9 该 **fragment 未写** `bootmode` —— 若 **SoC 基线**已在 **`extcon_usb`** 或上游节点提供，则 **沿用基线**；**不要**仅从老树机械拷贝 **`bootmode = <&chosen>;`** 除非新平台文档/基线明确要求且驱动仍解析。

#### `remote-endpoint`（**必须从芯片平台基准 dtsi 解析**）

- **含义**：USB **图（graph）** 里 **`extcon_usb` 端口**与 **`ssusb` / `tcpc` / `otg` 等** 的 **`endpoint` 互联**；**板级数值与 phandle 随平台变化**，**不能**从老树或它项目照抄。
- **操作步骤（建议）**：
  1. 打开 **同芯片、同大版本** 的 **MTK 平台基准 dtsi**（及 **Type-C / `ssusb` / `extcon_usb` 所在 include 链**）。
  2. 搜索 **`extcon_usb`**、**`remote-endpoint`**、**`usb-role-switch`**（或 **`connector` / `ports`** 命名），定位 **成对 `endpoint` 与 `remote-endpoint = <&…>`**。
  3. 若 **产品板**仅需改 **charger 绑定**：在 **`tc_charger.dtsi` 同类 fragment** 中 **只覆盖 `charger`**；**`remote-endpoint` 若基线已完整则不动**；若 **基线缺省或改版**：按 **基准 dtsi** 补全 **两端 label**，**`[REVIEW]`** `dtc` / 实机 USB 角色切换。

#### 迁移动作小结

1. **删除**以老树 **`mediatek,extcon-usb` + `&switch_chg`** 为模板的 **板级整块覆盖**思路；改 **对齐新分支 fragment + SoC 基线**。
2. **`charger`**：**`&switch_chg`→`&tc_chgtype`**（与新 **`tc_chgtype` / `tc_charger`** 拓扑一致）。
3. **`compatible` / `remote-endpoint` / 图结构**：**只信芯片平台基准 dtsi + 6.12 驱动表**；必要时与 **USB 角色 / Type-C 专项文档或项目内 bridge skill** 交叉。

### `tran_auto_test` → `tc_auto_test`（老 → 新：compatible + 节点名）

典型老树仅为：

```dts
tran_auto_test: tran_auto_test {
	compatible = "tran,auto_test";
	status = "okay";
};
```

**迁到 6.12 时须改为**：

```dts
tc_auto_test: tc_auto_test {
	compatible = "tc,auto_test";
	status = "okay";
};
```

**执行清单**

1. **`compatible`**：**`tran,auto_test`** → **`tc,auto_test`**（与 **`kernel_device_modules-6.12/.../transsion/tc_auto_test.c`** 中 **`tran_auto_test_match[]`** 一致）。
2. **节点 label / 节点名**：**`tran_auto_test:`** → **`tc_auto_test:`**（与驱动文件 **`tc_auto_test.c`** / 模块 **`TC_AUTO_TEST`** 命名一致，便于板级与文档对齐）。
3. **phandle / 引用**：在 **板级 dtsi、overlay、aliases** 中搜索 **`tran_auto_test`**、**`&tran_auto_test`**，全部改为 **`tc_auto_test`** / **`&tc_auto_test`**；若有 **其它节点 `phandle = <&tran_auto_test>`** 一并更新。
4. **`[REVIEW]`**：合入后在已收窄路径下执行 **`rg "tran,auto_test|tran_auto_test"`**，预期 **零命中**（除非项目声明并存例外）。

### `tran_otg` 设备树（`tc_otg_ctrl.c` → `tc_otg_dts_parse`）

以下属性均在 **`compatible = "tran,otg_fun"`** 节点上解析；未列出者 = 非本函数读取（GPIO/电源时序等由 **pinctrl** 子节点状态名 **`meta_gpio_*`、`otg_gpio_*`、`drvvbus_*`、`otg_dcp_*`、`otg_ovp_*`** 等配合硬件，不在本节逐项展开）。

| 属性名 | 类型 / 默认 | 功能（运行态语义） |
|--------|-------------|-------------------|
| **`support_otg_dcp`** | bool，默认 **false** | 使能 **USB2.0/BC 侧 DCP 相关 GPIO 路径**：`usb20_otg_dcp()`、`usb20_otg_ovp()` 才会动作；为 **false** 时整条 **otg_dcp / ovp** 控制直接 return。与 **反向充电模式** 组合：非 PD 分支下 **文件传输模式** 会关 DCP/OVP，**反向充电** 且在低温区会重新打开以便对端 BC1.2 检测（见 `tc_otg_set_vbus`）。 |
| **`pd_reverse_chg_support`** | bool，默认 **false** | **PD Type-C 反向充电（SRC/SNK 切换、DVCHG boost 与 PMIC OTG 协同）** 路径。为 **true** 时：`usb20_otg_dcp()` **提前 return**（不再走纯 DCP 管脚 toggling）；**开 OTG** 时走 **`dvchg_enable_otg` + `charger_dev_enable_otg`**，并可开 **PFM**；**Vbus short** 走 **PD hard reset / 恢复 work** 而非简单关 OTG。**为 false** 时走 **DCP+OVP+外部 OTG GPIO** 那一套（见下行）。 |
| **`otg_dcp_by_pmic`** | bool，默认 **false** | 为 **true** 时 **`usb20_otg_dcp()`** 只打印 **“en by pmic”** 并 **不切换 pinctrl**（代码里 PMIC 使能 **被注释掉**，属占位/硬件未接 GPIO 场景）。 |
| **`otg_dcp_ctrl_type`** | u32，默认 **`1`**（`TRAN_OTG_DCP_CTRL_BY_EXTERNAL_DEVICE`） | **`2`** = `TRAN_OTG_DCP_CTRL_BY_IC`：解析后 **强制** `otg_dcp_by_pmic = 1`。用于声明 **DCP 控制由充电 IC** 而非外部 GPIO。 |
| **`otg_avoid_hl7139a_step`** | bool，默认 **false** | 仅当 **`pd_reverse_chg_support`** 生效。为 **true** 时在开关 OTG 前后对 **`primary_dvchg`** 调用 **`charger_dev_disable_otg_step`**，避免 **HL7139A + 无线等场景下 Vbus 阶梯** 导致 **U 盘等工作异常**（注释原文：Sandisk disk）。 |
| **`support_ext_otg`** | bool，默认 **false** | 为 **true** 时 **`usb20_extern_otg_ctl()`** 才切换 **`drvvbus_high/low`** pinctrl，用于 **外部 5V 升压/供电使能** 类硬件。 |
| **`tc_otg_boost_curr_max`** | u32（µA），默认 **`2000000`** | **Boost/OTG 输出电流上限**；进入 OTG 时 **`charger_dev_set_boost_current_limit`** 的基础值（无动态 **`lmt_boost_cur`** 时）。 |
| **`tc_otg_boost_curr_min`** | u32（µA），默认 **`500000`** | **高温等场景下限**：电芯温度 **≥ `otg_revercharge_limit_temp`** 时 **`boost_cur` 被钳到该值**（log：**“limit 500mA”**）；与 **`lmt_boost_cur`** 组合时也会 **不低于** 该下限。**注意**：驱动里若读 **min 失败** 有一段 **误写 `tc_otg_boost_curr_max`** 的笔误，遇异常默认电流时请对照源码与实机 log。 |
| **`otg_revercharge_limit_temp`** | s32（℃），默认 **45** | **反向充电过热关断/降档主阈值**：`>=` 此温度时反向充电模式会 **退回文件传输** 或 **把 boost 限到 min**；work 里 **`otg_high_temp_flag`** 亦据此置位并 **关 10W 类 boost** 或发 **hardreset**。 |
| **`otg_reverse_chg_curr_lmt`** | u32（µA），默认 **0** | **第二段温区限流**：仅在 **`TC_OTG_REVERSE_CHG`** 且电芯温度 **≥ `otg_reverse_chg_limit_temp_step1`** 时，把限制电流设为 **`tc_otg_boost_curr_max - otg_reverse_chg_curr_lmt`**（即从最大 **扣减** 固定 µA）。**0** 表示不按此路径扣减（仍可能走其它分支）。 |
| **`otg_reverse_chg_limit_temp_step1`** | s32（℃），默认 **42** | **第一段「减功率」温度门限**：达到后按上条 **降低 boost limit**；与 **`otg_reverse_chg_recovery_area`** 构成 **降额 / 恢复** 迟滞。 |
| **`otg_reverse_chg_recovery_area`** | s32（℃），默认 **3** | **迟滞带**：温度 **≤ step1 − area** 时清除 **`lmt_boost_cur`** 并 **恢复到 `tc_otg_boost_curr_max`**；高温恢复时也要 **低于 `otg_revercharge_limit_temp − area`** 才认为可 **恢复正常反向充电**。 |
| **`boost_period`** | u32，默认 **20** | 读入 **`wdt_polling_interval`**，当前源码 **仅打印、未参与 hrtimer 周期**（定时 work 仍多为 **固定 2s** 的 `ktime_set(..., 2000*1e6)`）。属 **预留/未完接线** 或仅作 **日志核对**；若周期与文档不一致以代码为准。 |

**与 `mtk-adapt-template-basic-charging-capability` 的对应**：该模板 **`tran_otg` 常态保留** 给出 **`pd_reverse_chg_support`、`tc_otg_boost_*`、`otg_reverse_chg_*`、`otg_revercharge_limit_temp`** 等 **推荐默认整组**（含 **10 W / 6 W** 对 `tc_otg_boost_curr_max` 的注释）；语义即上表各属性列。其余 **DCP/外部 OTG** 等开关仍按硬件选配。

### `tran_otg` 迁移工作流（**仅 老分支 → 新分支**；编排器引用）

本流程 **不考虑**「新树 → 老树」落盘。迁移目标为：把 **5.10 老树 `tran_otg`** 合入 **6.12 新 DTS**，新侧 **`tc_otg_dts_parse`** 可读项比老树多时，**老树未写的属性直接用模板默认** 补全。

#### 1) `compatible` 必须核对

- 老树节点 **必须为 `compatible = "tran,otg_fun"`**（与 **`tran_otg.c`（5.10）** / **`tc_otg_ctrl.c`（6.12）** 的 `of_match` 一致）。
- 若老 DTS 写成其它串：**停止**按标准 OTG 节点自动生成新侧内容，标 **`[REVIEW]`** 请用户确认。

#### 2) 新树属性更多、老树常缺配

- **6.12** 可读项见上表（含 **`pd_reverse_chg_support`** 等）。**老树**可能仅有 **`status = "okay"`** 或少量项。
- **规则**：凡 **6.12 `tc_otg_dts_parse` 会消费**、而 **老树 DTS 未出现** 的属性，**优先**按 **`mtk-adapt-template-basic-charging-capability`** **「`tran_otg` 常态保留」** 整组写入，再用 **本 skill 上表** 核对类型与语义；仍缺项才按驱动隐式默认补齐。**不要**为「老树没写过」而留空——应 **显式写出** 并标 **`[REVIEW]`**（见 §4）。

#### 3) **老 → 新** 属性名映射（老树有值时，写入新 DTS 须用新名）

| 老（5.10，`tran_otg_dts_parse`） | 新（6.12，`tc_otg_dts_parse`） | 说明 |
|----------------------------------|-------------------------------|------|
| **`otg_boost_curr_max`** | **`tc_otg_boost_curr_max`** | µA |
| **`otg_boost_curr_min`** | **`tc_otg_boost_curr_min`** | µA |

其余在 **`tran_otg_dts_parse` / `tc_otg_dts_parse`** 中 **同名** 的项（如 `support_otg_dcp`、`otg_revercharge_limit_temp`、`boost_period` 等），一般 **键名不变、数值从老树拷贝**；仍建议对两侧 `*_dts_parse` **`rg` 一次** 防版本差。

**老树有、新树 `tc_otg_dts_parse` 不读** 的项（如 **`fake_typec_otg_detect`**、**`otg_special_market_boost_curr`**、**`market_filter_str`**）：**不**写入 6.12 节点体，在 **`/* SOURCE: OLD … */`** 或简报中说明 **「老树专有，新栈无同名解析」**，标 **`[REVIEW]`**。

**新树专有、老树未配** 的项（典型 **`pd_reverse_chg_support`**）：用 **模板默认**（上表多为 **false**）写入新 DTS，并 **`[REVIEW]`**（是否需 **true** 由硬件/反向充电方案决定）。

#### 4) **生成结束后（`[REVIEW]` 纪律）**

凡满足下列之一，在 dtsi 或简报中 **显式标注 `[REVIEW]`**（可写 **`/* [REVIEW] template default per bridge + basic-charging skill */`**）：

- 来自 **§2 模板补全**、**非**老树 DTS 原值的 6.12 属性；
- **`pd_reverse_chg_support`** 等与 **反向充电 / boost 限流 / 温控** 强相关的开关；
- 与 **现网新树 `tran_otg`** 合并时，以 **更保守或现网为准** 的 diff 结论。

便于合入前做 **OTG / 反向充电** 实机核对。

## 建议的工具命令（在工作区内）

- 老驱动：**`rg "of_match|tran,chg_fun|tran_charger_parse_dt|pcb_temp|jeita_|tran,auto_test|tran,smart_charging|transsion, water_detect|water_detect_parse_dt|tran,pid_chg_algo|pid_chg_algo|transsion,ambient_detect|transsion,temp_forecast|cable_imp|pe20_ichg|tc30_ichg|hvdcp20_ichg|mediatek,extcon-usb|extcon_usb" drivers/power/supply`**
- 新驱动：**`rg "single_batt_level|tpcb_ichg|tbat_ichg|tc_parse_single_batt|support_alg|tran,otg_fun|tc_otg_dts_parse|tc,auto_test|tc_auto_test|transsion, water_detect|tc_water_detect|tc,pid_chg_algo|pid_chg|tc,ambient_detect|tc,temp_forecast|ta_ichg_level_threshold|chr_volt_input_cur|chr_volt_chg_cur|charger_current_limit|pd_vbus_low_bound|tc_chgtype|extcon_usb" drivers/power/supply/transsion`**
- **USB 图 / `remote-endpoint`**（多在 **`drivers/usb`** / **`arch/.../dts`** 而非 `transsion` 单目录）：在 **SoC 基准 dtsi** 下 **`rg "extcon_usb|remote-endpoint" arch/arm64/boot/dts/mediatek`**（路径按芯片收窄）。

路径以用户工程 **`kernel-5.10`** / **`kernel_device_modules-6.12`** 为准；**UNC/网络盘** 大目录搜索时 **尽量收窄子路径**，避免全树超时。

## 与 `tran-projects-config-migrate-dtsi-dws` 的关系

| 本 skill | migrate skill |
|----------|----------------|
| **为什么** 老属性这样写、**新树哪几个属性承接**、**数值能否直拷** | **从哪里拷到哪里**（路径、板级 include、DWS、bootloader、GPIO、KO） |
| 驱动级 **语义 + 转换** | **流程 + 清单 + 合入纪律** |

二者可同时启用：本 skill 出 **对照与 CONVERT 注释**，migrate skill 保证 **目录与构建链不断**。

## 修订记录（摘要）

| 日期 | 摘要 |
|------|------|
| 2026-05-12 | **`tran_otg` 迁移工作流**：**仅老→新**；compatible；**`otg_boost_*`→`tc_otg_boost_*`**；老树缺参 **模板默认 + `[REVIEW]`**；摘要表 **`tran_otg`** 行指向该节。 |
| 2026-05-12 | **`tran_auto_test`→`tc_auto_test`**：摘要表 + 正文 compatible / 节点 / phandle / **`[REVIEW]`**。 |
| 2026-05-12 | **`smart_charging`（`tran,smart_charging`）**：摘要表 + 正文 **老→新**（删节点、`smartchg_min_cur`↔`smtchg_curr_min`、无 DT 注册时的 **`[REVIEW]`**）。 |
| 2026-05-12 | **`water_detect`（`transsion, water_detect`）**：摘要表 + 正文 **`scheme` 5.10↔6.12 对照表**、**`bootmode` 弃用**、**compatible 空格**、probe 依赖与 **`[REVIEW]`**。 |
| 2026-05-12 | **`pid_chg`**：**`tran,pid_chg_algo`→`tc,pid_chg_algo`**；**`ambient_temp` / `target_temp_array`** 与 **`power_level` 五档**；属性语义表与 **`[REVIEW]`**（证据：`tc_charger.dtsi` 模板）。 |
| 2026-05-12 | **`ambient_detect` / `temp_forecast`**：**`transsion,*`→`tc,*`**；**`pa_temp_gap` / `machine_gap` / `orgin_rate`** 注意项；lj6↔lj9 **`tc_charger.dtsi`** 对照。 |
| 2026-05-12 | **`support_alg` 子节点**：**`&pe2`/`&tc30`/`&hvdcp20`/`&pdc`→`&tc_pe2`/`&tc_30`/…**；**`chr_volt*`**、**`vbat_threshold` µV**、**`pdc` 字段改名**；**`transsion-dcp-fastcharge-probe`** 交叉。 |
| 2026-05-12 | **`extcon_usb`**：**新分支为准**；**6.12 Tran extcon vs `mediatek,extcon-usb`**；**`charger`→`&tc_chgtype`**；**`remote-endpoint` 跟 SoC 基准 dtsi**；lj9 fragment 证据。 |
| 2026-05-13 | **`tran_otg`**：与 **`mtk-adapt-template-basic-charging-capability`**「**`tran_otg` 常态保留**」交叉引用；迁移 **§2** 老树缺参时 **优先常态保留整组** 再核对上表。 |
| 2026-05-13 | **`temp_forecast` / `pa_temp_gap`**：老树无则 **默认 `<500>`**（有量产基准则从基准），与 **basic-charging-capability** 对齐。 |
| 2026-05-13 | **老 `mediatek,charger` &charger**：**DROP 忽略表**（`algorithm_name`、`power_path_*`、`disable_pd_dual`、`charger_configuration`、`multi_battery_cv`+`battery_cv`、细分 `usb_charger_current_*`、Apple/TA-AC/host、`enable_min_charge_temp` 等）；**`single_batt` USER**（SW JEITA 门限簇、`ffc_*`、`non_ffc_eoc`、`dv2_ffc_gera_*`）；**`min_charger_voltage_1/2`+`max_dmivr_charger_current`→`dynamic_mivr_vol`**；**`max_charger_voltage` 同名同步**；**`ambient_temp`/`target_temp_array`→`pid_chg`**。 |

## 边界

- 本 skill **不**替代芯片原厂或项目 **电池曲线签字**；**FFC、单电芯分段 CV、`battery_table`** 仍以 **电芯/BA** 为准。
- **高通 / 非 MTK** 栈请走对应平台 skill；本 skill 默认 **Tran + MediaTek KDM + transsion 充电目录**。
