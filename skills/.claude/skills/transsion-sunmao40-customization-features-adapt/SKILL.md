---
name: transsion-sunmao40-customization-features-adapt
description: >-
  Customization features adapt：只指导「客制化特性」如何适配。柱 3 **默认在对话里口述**（见 RULE-0「柱 3 口述输入」）；可选参考 **`pillar3-customization-input.md`**（表格挤、不必强填）。特性键 **`RULE-1`～`RULE-4` 与 `SM40-01`～`SM40-33` 均为客制化**。执行者把口述整理成「要做 / 不做 + 参数」后再落盘；分流在 mtk-adapt-template-router。
disable-model-invocation: true
---

# Transsion 榫卯 4.0 客制化（合并版）

**Customization features adapt（客制化特性适配）**：本 skill **只**收「怎么做适配」的规则与清单。`SM40-*` 对齐 **榫卯 4.0 飞书**章节号；`RULE-*` 多为 **合并前柱 3 模板 skill**（及从 basic-charging 摘录的客制化块）沿用下来的 **稳定特性键**，便于与 **`mtk-adapt-template-router`** 分流话术一一对应。**二者都是客制化**，没有「RULE 不算特性」的语义；区别见 **RULE-0「为何特性键里既有 RULE- 又有 SM40-」**。**柱 3 执行范围**以 **对话里用户口述的清单** 为准（可选对照 **`pillar3-customization-input.md`**）；**不负责**分流判定——那一步在 **`mtk-adapt-template-router`**。

> 飞书总来源：《[MTK]榫卯4.0 客制化原理以及验证方法》（SM40 各节标注原章节号）。目录名 `transsion-sunmao40-customization-features-adapt` 体现 **Customization features adapt**。

## 章节目录

### RULE — 柱 3 模板沿用键（与 router 分流话术对齐）

> 表内 **特性键** 与下列 **完全一致** 即跳转到对应 `## RULE-x` 节；**均为客制化**，非「非 SM40 即非特性」。柱 3 做哪几条以 **用户口述（或可选 `pillar3-customization-input.md` 表）** 为准。

| 编号 | 主题 |
|------|------|
| RULE-0 | 与 router 的分工（本文件不收分流） |
| RULE-1 | 通用「其它」客制化：占位模板 |
| RULE-2 | 关机充电动画（KPOC），与 **SM40-16** 正文交叉引用 |
| RULE-3 | 开机 / 关机工模 |
| RULE-4 | `tc_charger.dtsi` 客制化块注释保留 |

### SM40 — 榫卯 4.0 飞书条目编号

| 编号 | 主题 |
|------|------|
| SM40-01 | 防烧高温检测和提示 |
| SM40-02 | 电池健康度 |
| SM40-03 | 低电量榨取（硅负极） |
| SM40-04 | C2C 反向充电 |
| SM40-05 | 高低温提示语 |
| SM40-06 | Shipmode（运输节电） |
| SM40-07 | 电池长寿命循环降 CV |
| SM40-08 | 旁路充电 2.0 |
| SM40-09 | 全场景旁路充电 |
| SM40-10 | 差旅疾充（TCE） |
| SM40-11 | 无线旁路充电（磁吸风扇） |
| SM40-12 | 多场景充电 PID |
| SM40-13 | 端口防腐蚀 |
| SM40-14 | 电池自修复 |
| SM40-15 | 三档充电 |
| SM40-16 | 关机充电动画（KPOC） |
| SM40-17 | 端口液体检测和提示 |
| SM40-18 | 高温不报百 |
| SM40-19 | AI 智能充电保护 |
| SM40-20 | 自定义充电保护 |
| SM40-21 | 充电 Trancare 埋点 |
| SM40-22 | 云控（CloudEngine） |
| SM40-23 | 欧盟加密电池信息显示 |
| SM40-24 | 单双电芯兼容 |
| SM40-25 | 低功率充电增强 |
| SM40-26 | 温控充电（已作废） |
| SM40-27 | ro 无线充电功率（动画） |
| SM40-28 | ro 无线反向充电 |
| SM40-29 | ro 有线充电功率（动画） |
| SM40-30 | ro 充电动画总开关 |
| SM40-31 | 过压保护提示 charger_voltage_ovp |
| SM40-32 | 无线磁吸充电宝图标 |
| SM40-33 | 无线磁吸风扇充电动画 |

---

## 路径变量（禁止写死单板目录名）

以下各章凡写「见路径变量」均指本节。

| 变量 | 含义 |
|------|------|
| `${AOSP_ROOT}` | Android / AOSP 工程根目录 |
| `${project_full}` | Tran 工程全名（如 `cn6_h581`），见 `vendor/transsion/projects/${project_full}/` |
| `${mtk_platform_lower}` | 从 `vendor/transsion/projects/${project_full}/ProjectConfig.mk` 解析 `MTK_PLATFORM` 转小写（如 `mt6858`） |
| `${kdm_root}` | KDM 内核树，如 `kernel/kernel_device_modules-6.12` / `kernel/kernel_device_modules-6.6` / `vendor/kernel/kernel_device_modules-6.1`（随 Android 版本选择） |
| `${charge_overlay}` | 充电 DTS overlay 根，常见 `${kdm_root}/arch/arm64/boot/dts/mediatek/charge/${project_full}/`（以实际树为准） |
| `${kernel_dws}` | `vendor/mediatek/proprietary/tools/dct/dws/${mtk_platform_lower}/${project_full}.dws` |
| `${pl_codegen_dws}` | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/${project_full}/dct/dct/codegen.dws` |
| `${custom_kernel_dws}` | 若存在：`vendor/mediatek/proprietary/custom/${project_full}/kernel/dct/dct/codegen.dws` |
| `${lk2_project_mk}` | `vendor/mediatek/proprietary/bootable/bootloader/lk2/project/${project_full}.mk` |
| `${tran_projectconfig}` | `vendor/transsion/projects/${project_full}/ProjectConfig.mk`（若存在 `vendor/vendor/transsion/...` 须在 `${AOSP_ROOT}` 内做规则内回退） |
| `${defconfig_file}` | 平台 defconfig 文件名（随芯片/内核变化），位于 `${kdm_root}/arch/arm64/configs/` 或厂商指定 configs 目录 |
| `${ko_order_table}` | 项目 `ko_order_table.csv`（路径随平台发布，在 `${AOSP_ROOT}` 下按项目名/芯片检索） |
| `${meta_tran_chg_cpp}` | Meta 充电工模常见路径：`vendor/mediatek/proprietary/hardware/meta/common/src/tran_chg/tran_chg.cpp`（以分支为准） |

**纪律**：先解析 `project_full` 与 `mtk_platform_lower`，再拼接路径；禁止从 AOSP 根或整棵 `kernel-*` 无边界盲 `grep` 反推工程名（与 `mtk-adapt-template-router` 一致）。

---

## RULE-0 — 与 `mtk-adapt-template-router` 的分工

- **分流**（一级：器件 / 基本充电能力参数 / 客制化特性；二级：KPOC、工模、其它客制化等）**只**在 **`mtk-adapt-template-router`** 及其指向的 **柱 1 / 柱 2** skill 中维护；本文件 **不**重复三柱顺序、最小输入契约、输出契约、强制 Read 表等。
- 当 router 已判定进入 **客制化特性** 且执行者需落盘时：**`Read` 本文件**，按 **用户口述中明确「要做」** 的 **RULE-1～4 / SM40-01～33** 各节执行（**均为客制化**；键名差异见下 **「为何特性键里既有 RULE- 又有 SM40-」**）。若用户同时提供了 **`pillar3-customization-input.md`**，**口述优先**；二者冲突时 **以对话为准** 并反问确认。
- **基本充电能力参数**（非「特性」）仍以 **`mtk-adapt-template-basic-charging-capability`** 全文为准；其中 **仅「客制化块」注释保留规则**摘录为本文 **RULE-4**，避免与整份 basic 能力模板混淆。

### 柱 3 口述输入（默认）

- 用**自然语言、分条说**即可，**不必**压成表格，也**不必**把参数挤成一行 `键=值;键=值`。**口述优先**；**`pillar3-customization-input.md`** 仅供你自己整理时**可选**对照。
- **每条特性尽量说清楚三件事**（说不清的标明「待确认」）：
  1. **编号**：`RULE-n` 或 `SM40-xx`（与本文 **章节目录** **逐字一致**）。
  2. **做不做**：本项本次 **要做** 还是 **不做**。不做且柱 3 完全没工作量：说一句 **「此项特性无适配工作量」** 即可。
  3. **具体条件**：电压/温度/电流、接哪个 GPIO、改哪个宏或哪个文件路径等——**想到一条说一条**；很长的 dtsi 可以 **分几条消息** 贴。
- **KPOC**：**RULE-2** 与 **SM40-16** 只说一个「要做」，避免两套动画重复改。
- **执行者**：先把口述 **整理成短清单**（特性键 × 要做/不做 × 关键参数），**向用户回述一遍确认**后再落盘；信息不够就反问，**不要猜**。

### 柱 3 执行范围（口述与可选输入表）

- **输入**：默认以 **本任务对话中用户口述** 为准。若用户另行提供 **`pillar3-customization-input.md`**，可作补充；**口述与表冲突时以对话为准**，并反问确认。
- **处理**：**仅**对用户 **明确说要做** 且 **特性键** 合法（与章节目录一致）的项落盘。用户 **明确说不做** 或未提及的项：**不改码**。**禁止**对用户没说「要做」的 RULE/SM40 擅自改参。
- **收口**：列出 **章节目录有、但用户本次对话未声明「要做」** 的 RULE/SM40（仅提示，不代为开关）。用户已说「不做」或无工作量的可简短注明。

### 为何特性键里既有 `RULE-` 又有 `SM40-`？会不会「解析」出错？

- **没有两套语义**：凡出现在 **章节目录** 与全量表中的 **`RULE-1`～`RULE-4`、`SM40-01`～`SM40-33`**，在柱 3 里 **一律视为客制化特性**；**不存在**「带 `RULE` 前缀就不算榫卯客制化」的规则。
- **`SM40-xx` 从哪来**：对齐飞书《[MTK]榫卯4.0…》**章节编号**，方便产品 / SCM 把飞书清单逐条映射到表的 **特性键**。
- **`RULE-1`～`RULE-4` 从哪来**：合并本 skill 之前，**`mtk-adapt-template-router`** 已用 **RULE-2（KPOC）**、**RULE-3（工模）**、**RULE-1（其它占位）**、以及从 **basic-charging** 抽出的 **客制化注释块（RULE-4）** 指向独立模板 skill；合并后 **保留原特性键字符串**，避免「router 写 RULE-2、表里只有 SM40-16」时执行者对不上行。**不是**「RULE = 非客制化」——**RULE-2/3/4 同样是客制化**，只是历史键名未整体改成 `SM40-xx`。
- **「解析」指什么**：本流程 **没有**「只认 `SM40-`」的机器解析；执行者以 **用户口述或可选输入表中的特性键字符串** 与本文 **`## RULE-x` / `## SM40-xx` 标题逐字匹配** 跳转即可。**会出问题的情况**只有：拼写错误、多空格、或自创键名却未走 **RULE-1** 占位——与 `RULE` / `SM40` 前缀无关。
- **`RULE-2` 与 `SM40-16`（KPOC）**：正文交叉引用、**宏与资源纪律同一套**。口述里 **只承诺一个「要做」**（优先 **SM40-16** 与飞书一致；说 **RULE-2** 也行）。两个都说要做则 **改码只落地一次 KPOC**，并提醒用户二选一。

### 可选：`pillar3-customization-input.md`

- **约定路径**：`d:\Users\guansen.wang\.cursor\skills\pillar3-customization-input.md`（可拷贝到项目侧；若实际路径不同，任务内须显式声明 **`Read` 路径**）。
- **用途**：表格里 **示例列较密**，**不勉强阅读或填写**；若仍想用表自检，可只看 **特性键** 与 **是否需要支持**，**参数** 列可留空改在对话里口述。
- **不再使用**：`客制化特性支持情况*.csv` / `*.xls`、以及已废弃的 **`pillar3-customization-input.yaml`**。

### 书面整理 / 表格式纪要（可选）

0. **总原则**：**口述已足够**；本节仅在需要给第三方留纪要、或自愿维护输入表时使用。若整理成一行 `键=值`，多条仍可用英文 **`;`** 分隔。**SM40-14** 等多字段项，**口述时鼓励分句**；压成纪要时再合并。下表为 **「若要做该条，纪要里建议覆盖哪些信息」**。

1. **多条（纪要）**：`键=值`；多条用 **`;`** 分隔。例：`burn_max_temp=450;burn_gap_temp=30`。

#### 用户声明「要做」时：每条须交代清楚的配置（口述可分句；纪要可并成键=值）

| 特性键 | 须交代的主要配置（摘要；细节见各节正文） |
|--------|------------------------------------------|
| **RULE-1** | 自定义：`path=`、`node=`、`compatible=`、`action=` 等（见 **RULE-1** 输出模板）；无标准键名 |
| **RULE-2** | `TRAN_CHARGER_KPOC_ANIMATION=yes`；`CUSTOM_TRAN_LOGO=tran_logo_品牌`；与 **SM40-16** 资源路径 |
| **RULE-3** | `factory.ini` 的 `MenuItem` 取舍 + `ProjectConfig` 宏（`TRAN_BSP_CHARGE_TYPE_SUPPORT` 等，见 **RULE-3** 映射表） |
| **RULE-4** | 列举须解注的 `tc_charger.dtsi` / `&odm` 注释块名（或 `verify=与基线一致`）；见 **RULE-4** 示例块 |
| **SM40-01** | `port_burning`：`burn_max_temp`、`burn_gap_temp`、`burning_interval`、`normal_interval`、`control_gpio`…；KO/DWS 摘要 |
| **SM40-02** | `&charger`：`bat_health_cycle_base`、`bat_health_dec_times`；`ro.tr_battery.health.support=`… |
| **SM40-03** | `support_si_bat`、`si_bat_*`、`lk_charger` 启动电压相关；`TRAN_LOW_BATTERY_SUPPORT`；`ro.tr_battery.shutdown_lowvolt…` |
| **SM40-04** | `tran_otg`/`tc_otg`：`pd_reverse_chg_support`、`tc_otg_boost_*`、`otg_reverse_chg_*` 等（见 §SM40-04） |
| **SM40-05** | `&charger`：`batt_ht_*`、`batt_lt_*`、`kpoc_batt_*`、`*_dis_chg` / `*_code_dis_chg` 等成组属性 |
| **SM40-06** | `TRAN_SHIPPING_MODE_SUPPORT`；shipmode sysfs 节点路径；Meta 读写说明 |
| **SM40-07** | `support_long_life_recharger`；`tc_pe50.dtsi` `step_ffc_level*`；`single_batt_level*` |
| **SM40-08** | charger IC 节点 + `tc_charger` 旁路相关；`ro.tr_charge.bypass_def_on.support=`… |
| **SM40-09** | `support_allround_bypass`；`ro.tr_battery.full_scene_bypass_charging.feature.support=`… |
| **SM40-10** | `tc_pe50.dtsi` `&pe5`：`*_level_def_3`、`*_curlmt_3` 等；`ro.tr_tce.travel.feature.support=`… |
| **SM40-11** | `wireless_manager`：`support_magnetism_fan_*`、`magnetism_fan_bypass_aicr` |
| **SM40-12** | `tc_misc`、`pid_chg`、`ambient_detect`、`temp_forecast` 各节点关键属性（见 §SM40-12） |
| **SM40-13** | defconfig 两项；`phy_det`/`port_corrosion` 节点；KO 行；DWS 说明 |
| **SM40-14** | 见下 **SM40-14** 小节（`support_bat_self_repair`、`bat_repair_*`、两 `health_percent_*` 表） |
| **SM40-15** | `tc_pe50.dtsi` `&pe5` 三档数组、多电芯宏；`ro.tr_charging.animation.support=`… |
| **SM40-16** | 与 **RULE-2** 同宏 + BootLogo 资源路径摘要 |
| **SM40-17** | `water_detect`：`scheme`、`polling_interval` 等；器件 `high_precision` 等；KO 行 |
| **SM40-18** | `single_batt_level*`；`disable_high_temp_lock_uisoc`；长表 `dtsi:` |
| **SM40-19** | `ro.tr_battery.ai_charging_event_track…`；sysfs 路径（内核默认导入可写「仅核对」） |
| **SM40-20** | sysfs `tran_custom_disable_charger` 路径；无 dtsi 额外项可写「基线已支持仅核对」 |
| **SM40-21** | `tc_trancare.c` 枚举/case 变更说明（代码项，难用单行键值） |
| **SM40-22** | 云控 ID、`register_cloudengine_notifier` 段是否注册（见 §SM40-22） |
| **SM40-23** | owner 提供的文件/属性清单（原文待补齐） |
| **SM40-24** | `battery_prop.dtsi` `tran_Q_diff` 等；`tc_pe50` `support_multi_bat_parameter` 与 `bat0_*`/`bat3_*` 表 |
| **SM40-25** | `support_enhance_mode`；`pid_chg` `target_temp_array_enhance` 与常规表 |
| **SM40-26** | 不应做；不做且无工作量 → 注明 **「此项特性无适配工作量」** |
| **SM40-27** | `ro.tr_charging.animation_wireless_power=…`；`*.mk` 片段或「无 dtsi」 |
| **SM40-28** | `ro.tr_battery.wireless_reverse_charge.support=…` |
| **SM40-29** | `ro.tr_charging.animation_wire_power=…` |
| **SM40-30** | `ro.tr_charging.animation.support=…` |
| **SM40-31** | `charger_voltage_ovp=` 四项 µV 或 `dtsi: charger_voltage_ovp = <…>;` |
| **SM40-32** | 仅核对：不做 +「此项特性无适配工作量」；调无线 fragment：要做 + `wireless_*` 片段 |
| **SM40-33** | `ro.tr_game.magnetic_fan.support=…`；与 **SM40-11** 联调说明 |

2. **单位**：跟在值后括号，如 `burn_max_temp=450(0.1°C)`、`charger_voltage_ovp=…(µV 四项见正文)`。  
3. **仅开关**：可口述「按 RULE-4 解注」；纪要可写 `enable=true` / `support_xxx=true`。**不做**时写 `support_xxx=false` 或「不启用」。  
4. **整段 dtsi**：口述分条贴；纪要可用 `dtsi:` 前缀一行浓缩，过长仍建议 **对话里贴全文**。  
5. **KPOC**：`TRAN_CHARGER_KPOC_ANIMATION=yes;CUSTOM_TRAN_LOGO=tran_logo_品牌小写`。  
6. **RULE-1 目录外**：`path=…;node=…;compatible=…;action=启用|关闭`（键名可酌增，须可读）。  
7. **SM40-14**：口述逐句说清开关、三标量、两数组；压成纪要一行时可与可选输入表中 **SM40-14** 行示例同形（尖括号须规格书，勿照抄占位）。

#### 示例（**SM40-14** 电池自修复）

**须配置的项**（`&charger`，见正文）：`support_bat_self_repair`（开关）；`bat_repair_cycle_threshold`、`bat_repair_done_uisoc`、`bat_repair_done_vbat`；`health_percent_cycle_table`、`health_percent_add_table`。

- **支持** → 口述或纪要中给出 `support_bat_self_repair=true`（或 dtsi 语义等价 `yes`）；**不支持** → `false` 或说「不启用自修复」。  
- **三个标量**（**实值须电池组 + binding 确认**）：`bat_repair_cycle_threshold=200`、`bat_repair_done_uisoc=5`、`bat_repair_done_vbat=3400`（占位，勿未确认照抄）。  
- **两数组**：`health_percent_cycle_table=<0 100 200 500>`、`health_percent_add_table=<0 1 2 5>`（格式示意，尖括号须规格书）。

**整段纪要（可选一行）**  
`support_bat_self_repair=true;bat_repair_cycle_threshold=200;bat_repair_done_uisoc=5;bat_repair_done_vbat=3400;dtsi:health_percent_cycle_table=<0 100 200 500>;health_percent_add_table=<0 1 2 5>;`

执行者：**以对话确认后的「要做」清单为准**；若用户维护了输入表，可交叉核对 **「是否需要支持」= 是** 的行，仍以 **口述冲突时对话优先**。

---

## RULE-1 — 通用「其它」客制化特性（占位模板）

> 合并自原 `mtk-adapt-template-feature-placeholder` 的适配规则（不含分流）。

### 适用范围

器件之外、且不属于「基础充电能力参数」的客制化需求，例如：客户定制充电策略开关；工厂 / 认证 / 老化 / 区域策略；平台默认之外的 feature 开关与参数联动。

### 最小输入（收集后再写清单）

- 特性名称 / 目标 / 生效范围（kernel、lk、preloader）/ 预期行为 / 触发与退出条件 / 与基线差异来源（历史项目 copy、客户需求、规范）。

### 输出（适配清单必备项）

- 特性分层归属（kernel、lk、preloader）；需修改文件；配置项与联动项；与平台基线差异项（标注 `基于历史项目 copy` 或 `客户定制`）；验证场景。

### 边界

- 不替代器件适配模板；若实为 **基础能力参数** 调整，转 **`mtk-adapt-template-basic-charging-capability`**（仍经 router 分流）。
- `tc_charger.dtsi` 的通用骨架、平台差异与参数化块，以 **basic-charging** 全文为准；**客制化块注释写法**见本文 **RULE-4**。

---

## RULE-2 — 关机充电动画（KPOC）

> 合并自原 `mtk-adapt-template-feature-kpoc-charging`。与 **SM40-16** 可交叉核对（SM40 偏飞书路径变量；本节偏 router 模板与 ProjectConfig 纪律）。

### 适用范围

开启或核对 **关机充电 / KPOC** 场景下的 **充电动画资源**（非 kernel 充电逻辑）；修改面在 **LK2** 与 **Tran `ProjectConfig.mk`**。

### 必配宏控（两处同时一致）

1. **LK2** — **文件**：`${lk2_project_mk}`（若工程为单层 `vendor/`，路径去掉一层 `vendor/`）。**宏**：`TRAN_CHARGER_KPOC_ANIMATION=yes`。产品不要动画时再改为 `no`，须与资源包一致。
2. **Tran ProjectConfig** — **文件**：`${tran_projectconfig}`。**宏**：`TRAN_CHARGER_KPOC_ANIMATION = yes`；`CUSTOM_TRAN_LOGO = tran_logo_<品牌名>`（`<品牌名>` 小写，如 `tecon`、`infinix`，以资源目录为准）。

### `ProjectConfig.mk` 修改纪律（与充电/KPOC 动画相关）

- **通常只动两类宏**：`TRAN_CHARGER_KPOC_ANIMATION`、`CUSTOM_TRAN_LOGO`。
- **不要**在 KPOC 专项里顺带批量改 `TRAN_PRODUCT_BRAND`、`TRAN_TARGET_DEVICE`、`TRAN_PRODUCT_MANUFACTURER`、`TRAN_PRODUCT_MODEL`、`TRAN_PRODUCT_NAME`（与充电/动画无直接关系）。
- **`CUSTOM_TRAN_LOGO` 后缀可与 `TRAN_PRODUCT_*` 不一致**：资源要求 `tran_logo_tecon` 而 `TRAN_PRODUCT_BRAND` 仍为参考机遗留时，**只改 `CUSTOM_TRAN_LOGO`**，除非用户另起「品牌信息统一」专项。

### 品牌名解析顺序

1. 同文件已有 `CUSTOM_TRAN_LOGO = tran_logo_xxx` → `<品牌名>` = `xxx`。  
2. `TRAN_PRODUCT_*` **仅作沟通佐证**，不得据此擅自批量改写。  
3. ODM `device.mk` 等仅佐证；**以 `CUSTOM_TRAN_LOGO` 与资源目录是否存在为准**。  
4. 冲突或缺失：**停止猜测**，向用户索要目标 `CUSTOM_TRAN_LOGO` 或资源包 logo 目录名。

### 不确定时

在相关行上加简短注释说明待确认；答复中列出「待用户确认」项。

### 验证清单

- LK：`TRAN_CHARGER_KPOC_ANIMATION=yes`；Tran：两项宏与 LK 语义一致；资源路径参与拷贝；实机关机插充确认品牌与动画。

### 边界

- **不**替代 charger IC、gauge、DTS 充电参数。充电电流/类型问题先走充电栈分析 skill，不单查 KPOC。

---

## RULE-3 — 开机工模 / 关机工模

> 合并自原 `mtk-adapt-template-feature-factory-mode` 的适配规则（不含分流）。

### 适用范围

开机工模、关机工模、工模进/出与 **充电链路联动**（是否限流、是否屏蔽策略）。**不**用于：KPOC 资源（**RULE-2**）；器件替换；纯 **基本能力参数**（走 basic-charging，经 router）。

### 最小输入

项目名与平台版本；工模类型；进/出条件；生效层级（preloader、lk、kernel）；对充电能力与策略的影响清单。

### 执行骨架

1. 识别工模入口层级（preloader、lk、kernel）。  
2. 梳理状态来源（bootmode、命令、节点、宏控）。  
3. 评估与 `tc_charger` / `tc_pe50` / gauge 的联动。  
4. 输出改动清单与验证场景（正常模式 + 工模模式）。  
5. 差异项标注 `基于历史项目 copy` 或 `客户定制`。

### 关机工模（Factory 菜单）

- **文件**：`vendor/mediatek/proprietary/custom/${project_full}/factory/factory.ini`（路径以实树为准）。  
- **`MenuItem` 建议**：`Battery & Charger(A);`、`USB(M);`、`OTG(M);`、`Slave Charger(A);`、`Wireless Charger(A);`、`USBTYPEC(A)`。  
- **条件**：无无线充电则去掉 `Wireless Charger(A)`；无 charge pump 则去掉 `Slave Charger(A)`；删减须在适配说明中写原因。

### 开机工模（ProjectConfig 与 Tranfac 映射）

- **文件**：`${tran_projectconfig}`。  
- **原则**：此处配的是 **ProjectConfig 宏**，不是直接改 Json key；TranfacVnd 按宏映射 USB 工模能力。  
- **摘录映射**（命中条件才生成菜单项；未命中不生成，避免菜单与硬件不一致）：

| 能力 | 宏 | 命中/规则摘要 |
|------|-----|----------------|
| RFC 快充 | `TRAN_BSP_CHARGE_TYPE_SUPPORT` 含 `rfc_charge` | `tranfac.usb.charge.rfc`；**非 18W 项目** |
| PE 快充 | 同上含 `pe_charge` | `tranfac.usb.charge.pe`；**18W 项目** |
| 无线充电 | 同上含 `wireless_charge` | `tranfac.usb.charge.wireless` |
| 三方电量计在位 | `TRAN_THIRD_FUEL_GAUGE = yes` | `tranfac.usb.charge.battery_check`（语义为三方 fuel gauge） |
| 反向充电 | `TRAN_REVERSE_CHARGE_SUPPORT = yes` | `tranfac.usb.charge.reverse`；阈值宏 `TRAN_REVERSE_CHARGE_THRESHOLD` |
| C2C 反向 | `TRAN_OTG_SW_C2C_SUPPORT = yes` | `tranfac.usb.charge.reverse_c2c` |
| 充电管控 | `TRAN_MIDTEST_CHARGE_CONTROL_SUPPORT = yes` | `tranfac.usb.charge.control` |

- **样例**：`TRAN_BSP_CHARGE_TYPE_SUPPORT = rfc_charge wireless_charge`、`TRAN_THIRD_FUEL_GAUGE = yes`、`TRAN_REVERSE_CHARGE_THRESHOLD = 10`、`TRAN_OTG_SW_C2C_SUPPORT = yes`。

### 输出模板

工模分层归属；需改文件；宏与配置项；进/出条件表；与充电联动影响；验证清单（正常进/出工模、充电行为符合预期）。

### 边界

- 不替代器件适配；纯基础充电参数仍转 **basic-charging**（经 router）。

---

## RULE-4 — `tc_charger.dtsi` 客制化块注释保留

> 摘自 **`mtk-adapt-template-basic-charging-capability`** §「客制化块」：只同步**适配规则**，不替代该 skill 全文（温区、LK 强约束等仍在 basic）。

### 规则（必须执行）

- 客制化开关或参数**须写进模板**（可默认不启用）。  
- 默认采用 **注释保留**，便于按项目解注。  
- 每个开关或参数在**同行或上一行**注释标明对应客制化特性。  
- 建议格式：`// 客制化特性-<特性名称>`。

### 默认注释示例（`&charger` / `&odm`）

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

### 归类与标注（与 basic 一致）

- `water_detect` / `tc_audio`：进水/进液类；默认不固化；可标 `[基于历史项目 copy，需项目复核]`。  
- `wireless_*`：无线充电相关；同上。  
- 其它客制化开关（如 `support_enhance_mode`、`support_long_life_recharger` 等）：按需启用并标复核来源。

---

## SM40-01 — 防烧高温检测和提示

> 飞书章节「一」。Wiki 元数据示例：文档 `NmIawLm1ViERpDkMsiycWbzgnbg`，ID `TVRod3PCsoMupsxVeJ3cRTAin9g`。

### 原理

插入充电器后循环检测小板 NTC；端口温度超过 `burn_max_temp`（且与上次不同）则上报 uevent、暂停充电；Framework/APP 弹高温窗；低于 `burn_max_temp - burn_gap_temp` 恢复充电。门限与 gap 对应设备树 `burn_max_temp`、`burn_gap_temp`（0.1°C）。

### 底软客制化

1. **DWS（NMOS 控制脚为输出）** — **文件**：`${kernel_dws}`、`${custom_kernel_dws}`（若有）、`${pl_codegen_dws}`。GPIO 输出方向、`def_mode`/`eint_mode`/`def_dir`/`out_high`、`inpull_*` 与原理图默认态一致；`varName0` 建议 `NMOS_CTRL_PIN`。
2. **设备树** — **文件**：`${charge_overlay}/tc_charger.dtsi`（或项目实际 include 的充电 fragment）。**节点**：`port_burning`：`compatible = "transsion,port_burning";`，配置 `burn_max_temp`、`burn_gap_temp`、`burning_interval`、`normal_interval`、`control_gpio`、`bootmode`（若驱动仍用）。
3. **KO** — **文件**：`${ko_order_table}`。**行**：`tc_port_burning.ko` → `${kdm_root}/drivers/power/supply/transsion/tc_port_burning.ko`（以树内为准），分区 `odm`。

**SM40-01 书写建议**：优先 **对话里分条口述**；若须留纪要再在对话中按 **SM40-01** 贴结构化草稿（**`1. 需求参数`** `1.1`～`1.6` 与 **`2. 模板示例`** `2.1`～`2.4`，与上文「底软客制化」第 2 条 `port_burning` 配置名一致；**不要**写「落点」等字样，路径变量见本文「路径变量」表）。可选输入表里不必挤 **参数** 列。

### 关联

`mtk-adapt-template-router`（柱3）、`mtk-adapt-template-basic-charging-capability`。

---

## SM40-02 — 电池健康度

> 飞书章节「二」。

### 原理

`bat_health_percent = 100 - (bat_cycle - bat_health_cycle_base) / bat_health_dec_times`；前 `bat_health_cycle_base` 次循环不计入衰减，之后每 `bat_health_dec_times` 次循环健康度降 1%。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi`
- **节点**：`&charger`
- **属性**：`bat_health_cycle_base`、`bat_health_dec_times`（须电池组确认；文档：≥33W 新项目默认 `bat_health_cycle_base = 100`）。
- **上层属性**：`ro.tr_battery.health.support`（非 dtsi，CMO/属性链配置）。

### 关联

`mtk-adapt-template-basic-charging-capability`（`eoc_scheme` / aging 相关段落）。

---

## SM40-03 — 低电量榨取（硅负极）

> 飞书章节「三」。仅硅负极电池方案。

### 原理

硅负极可将关机电压下探至约 3.0–3.2 V，使用 3.0–3.4 V 区间容量。

### 底软客制化

1. **Kernel** — **文件**：`${charge_overlay}/tc_charger.dtsi` — `&charger`：`support_si_bat;`、`si_bat_cycle_def`、`si_bat_cycle_vol`；`&lk_charger`（或等价节点）：`boot-battery-voltage`、`boot-voltage-level`、`low-bat-temp-boot-vbat`（单位按 binding）。电池表：同目录 `bat_setting/*battery_prop*.dtsi` 等由电池组对齐。
2. **LK2** — **文件**：`${lk2_project_mk}` — `TRAN_LOW_BATTERY_SUPPORT := yes`
3. **上层**：`ro.tr_battery.shutdown_lowvolt.feature.support`。

---

## SM40-04 — C2C 反向充电

> 飞书章节「四」。tOS16.1 / 16.2 / 16.3 策略差异以分支文档为准。

### 原理

手机作 PD Source 时，通过 hard reset 与能力重协商，在电量与协议条件满足时开放 5V/2A 等级反向供电（功率档因项目而异）。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi`
- **节点**：`tran_otg` / `tc_otg`（以 `of_match` 为准）
- **属性示例**：`pd_reverse_chg_support;`、`otg_revercharge_limit_temp`、`tc_otg_boost_curr_max/min`、`otg_reverse_chg_curr_lmt`、`otg_reverse_chg_limit_temp_step1`、`otg_reverse_chg_recovery_area`。

### 关联

`transsion-charger-dtsi-driver-bridge`（`tran_otg` 迁移）、`mtk-adapt-template-basic-charging-capability`。

---

## SM40-05 — 高低温提示语

> 飞书章节「五」。

### 原理

在高低温边界用温度档、恢复温度、notify code、vote（停充/HIZ/图标）及非充电场景 `*_dis_chg` 组，驱动停充、通知与 UI。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi` — **节点**：`&charger`
- **属性**：`batt_ht_*`、`batt_lt_*`、`kpoc_batt_ht_*`、`kpoc_batt_lt_*`、`batt_ht_temp_dis_chg` / `batt_ht_code_dis_chg`、`batt_lt_temp_dis_chg` / `batt_lt_code_dis_chg`（文档给 -19℃ / -10℃ / 0℃ 电池多套示例，按规格书择一）。

### 关联

`transsion-charger-dtsi-driver-bridge`、`mtk-adapt-template-basic-charging-capability`。

---

## SM40-06 — Shipmode（运输节电）

> 飞书章节「六」。

### 原理

PMIC/路径管断开 VBAT→SYS，极低待机；nQON 脉冲唤醒时序见器件 datasheet。

### 底软客制化

1. **内核**：实现 shipmode sysfs（文档示例 `/sys/devices/platform/charger/shipmode_enable`，以实际 charger 平台设备为准）。
2. **Meta / 关机工模** — **文件**：`${meta_tran_chg_cpp}` — `#if defined(TRAN_SHIPPING_MODE_SUPPORT)` 内 `open/write/read` 上述节点；写 `1` 后需 **足够延时** 再读回（文档约 10s 级）。
3. **编译宏**：在对应 `ProjectConfig.mk` / `*.mk` 打开 `TRAN_SHIPPING_MODE_SUPPORT`（入口随 Tran 集成方式检索）。

---

## SM40-07 — 电池长寿命循环降 CV

> 飞书章节「七」。与「电池缓释」互斥。

### 原理

循环超门槛后略降 CV，用略少可用容量换循环寿命。

### 底软客制化

1. **文件**：`${charge_overlay}/tc_charger.dtsi` — `&charger`：`support_long_life_recharger;`
2. **文件**：`${charge_overlay}/tc_pe50.dtsi` — `&pe5`：`step_ffc_level`、`step_ffc_level_*`（温区/CV/电流/截止/循环门槛矩阵，由电池组给表）。
3. **文件**：`${charge_overlay}/tc_charger.dtsi` — `&charger`：`single_batt_level`、`single_batt_level_*` 普充多段。
4. **迁移**：老 `mtk_pe50` → `tc_pe5` 须 `Read transsion-pe5-migrate-dual-cp-k612`。

---

## SM40-08 — 旁路充电 2.0

> 飞书章节「八」。

### 原理

利用 charger IC **power path**：适配器优先供系统；常通过将 charger 置 HZ 等进入旁路路径。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi` + **charger IC 节点**所在 dtsi（随 IC 驱动属性名变化，由 `mtk-adapt-template-device-charger-ic` 收敛）。
- **说明**：文档强调 IC 须支持 power path；`bypass_charger` 等 sysfs 由驱动提供（路径以实机为准）。
- **上层**：`ro.tr_charge.bypass_def_on.support`。

---

## SM40-09 — 全场景旁路充电

> 飞书章节「九」。

### 原理

相对旁路 2.0，对电池仍维持约 300mA 等策略，减轻反复掉电；`tc_charger.c` 中由 `support_allround_bypass` 选择 `tc_bypass_charger_hdlr` 与旧 handler。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi` — **节点**：`&charger` — **属性**：`support_allround_bypass;`（注释即回退旁路 2.0）。
- **上层**：`ro.tr_battery.full_scene_bypass_charging.feature.support`。

---

## SM40-10 — 差旅疾充（TCE）

> 飞书章节「十」。详设见文档内飞书链接。

### 原理

在机场/车站等 POI 放开温升限流，提高补电速度。

### 底软客制化

- **文件**：`${charge_overlay}/tc_pe50.dtsi` — **节点**：`&pe5`
- **属性**：多电芯 `bat0_*_level_def_3` / `bat0_*_curlmt_3`、`bat1_*`…；单电芯 `bat_tbat_level_def_3`、`bat_tpcb_level_def_3`、`bat_tpa_level_def_3` 及对应 `*_curlmt_3`（删除即取消）。
- **上层**：`ro.tr_tce.travel.feature.support`。
- **调试节点**：`chgspeed_ctl`、`pe50_debug`（以实机 sysfs 为准）。

---

## SM40-11 — 无线旁路充电（磁吸风扇）

> 飞书章节「十一」。

### 原理

无线 manager 识别磁吸风扇配件，打开无线旁路与 AICR，旁路不掉电。

### 底软客制化

- **文件**：`${charge_overlay}/` 内含 `wireless_manager` 节点的 dtsi（fragment 名以项目为准）
- **节点**：`wireless_manager`
- **属性**：`support_magnetism_fan_check;`、`support_magnetism_fan_bypass;`、`magnetism_fan_bypass_aicr = <...>;`（注释即关闭）。

### 关联

`transsion-wireless-bypass-fan`。

---

## SM40-12 — 多场景充电 PID 算法

> 飞书章节「十二」。

### 原理

小板 NTC + 电池 NTC + 功耗估计环境温度，PID 动态调流；含 ambient 估计与 temp_forecast。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi`（通常在 `&odm`）
- **节点**：`tc_misc`（`tc,misc_intf`）：`det_ibus_by_swchg`、`io-channels`、`tusb_div_res/vol`、温度边界等。
- **节点**：`pid_chg`（`tc,pid_chg_algo`）：`pid_array`、`ambient_temp`、`target_temp_array`、`power_level` 等。
- **节点**：`ambient_detect`（`tc,ambient_detect`）、`temp_forecast`（`tc,temp_forecast`）。
- **迁移**：老 `tran,pid_chg_algo` / `transsion,*` compatible 按 `transsion-charger-dtsi-driver-bridge` 与编排器 §9–§10。

---

## SM40-13 — 端口防腐蚀

> 飞书章节「十三」（端口防腐蚀条目）。

### 原理

GND 插入检测脚接 AP GPIO；无插入 CC 拉低，插入后轮询 CC，减缓进液后 CC 带电腐蚀。

### 底软客制化

1. **defconfig** — `${kdm_root}/arch/arm64/configs/${defconfig_file}`：`CONFIG_TC_PHY_INSERT_DET=m`、`CONFIG_TC_PORT_CORROSION=m`。
2. **DTS** — `${charge_overlay}/tc_charger.dtsi` 的 `&odm`：`phy_det`（`transsion,phy_det` + `phy,intr-gpio`）、`port_corrosion`（`transsion,port_corrosion`）。
3. **DWS** — `${kernel_dws}`、`${pl_codegen_dws}`、`${custom_kernel_dws}`：检测脚 **输入** 模式。
4. **KO** — `${ko_order_table}`：`tc_phy_insert_det.ko`、`tc_port_corrosion_prevention.ko`。

---

## SM40-14 — 电池自修复

> 飞书章节「十三」（电池自修复条目，与端口防腐蚀同号不同题）。

### 原理

深度放空后，在 0–5% SOC 以小电流修复；按循环表增加上报健康度。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi` — **节点**：`&charger`：`support_bat_self_repair;`、`bat_repair_cycle_threshold`、`bat_repair_done_uisoc`、`bat_repair_done_vbat`、`health_percent_cycle_table`、`health_percent_add_table`（删除/注释即关闭）。

### 柱 3 填写示例（电池自修复）

**口述即可**（分句说：开不开自修复；三个整数门槛；两个数组各有哪些数——**须规格书**）。若自愿维护 **`pillar3-customization-input.md`**：**「是否需要支持」= 是** 时 **参数** 列须写清每一项目标值（勿只写「要开功能」）；**示例** 列仅作格式参考。

| 列 | 填写要点 |
|----|----------|
| **特性键** | `SM40-14` |
| **是否需要支持** | `是`（本示例；不做该项则说「不做」或表内填 `否`，无工作量时说明 **「此项特性无适配工作量」**） |
| **参数（可选表内）** | 支持：`support_bat_self_repair=true;…`（见 **RULE-0** 示例）。**不支持**：`false` 或「不启用」。实值须电池组确认。 |
| **示例（格式参考）** | 见可选输入表 **SM40-14** 行；**不必强读** |

**逐项说明（口述或纪要均可）**

1. `support_bat_self_repair`：与是否支持自修复一致。  
2. `bat_repair_cycle_threshold`：整数；须电池组确认。  
3. `bat_repair_done_uisoc` / `bat_repair_done_vbat`：整数；单位见 binding。  
4. `health_percent_cycle_table` / `health_percent_add_table`：整段数组；可拆到多条消息。

**与 dtsi 对应关系**：`support_bat_self_repair` 对应解注 `support_bat_self_repair;`；其余键名与 `&charger` 中属性一一对应（见上文「底软客制化」列表）。

**长说明**：放在对话里即可，不必压回表格。

---

## SM40-15 — 三档充电

> 飞书章节「十四」。

### 原理

极速 / 智能 / 低温三档不同 `tbat/tpcb/tpa` 限流曲线（`*_level_def_[0..2]` + `*_curlmt_[0..2]`）；多电芯加 `batN_*` 与 `support_multi_bat_parameter`（文档属性名 `supprot_multi_level_charging` 以驱动 binding 为准）。

### 底软客制化

- **文件**：`${charge_overlay}/tc_pe50.dtsi` — `&pe5`：开启三档与多电芯宏；填入各档数组。
- **上层**：`ro.tr_charging.animation.support`。

---

## SM40-16 — 关机充电动画（KPOC）

> 飞书章节「十五」。

### 原理

KPOC 显示关机安全充电动画与品牌 LOGO。

### 底软客制化

1. **资源** — `vendor/mediatek/proprietary/external/BootLogo/logo/<分辨率>/<平台>/`（以 UI 交付为准）。
2. **Tran** — `${tran_projectconfig}`：`CUSTOM_TRAN_LOGO`、`TRAN_CHARGER_KPOC_ANIMATION = yes`、`TRAN_BOOT_LOGO` / `BOOT_LOGO`。
3. **LK2** — `${lk2_project_mk}`：`TRAN_CHARGER_KPOC_ANIMATION=yes`。
4. **排查**：`vendor/mediatek/proprietary/external/charger/transsion_charger/libtranshowlogo/` 像素解析函数。

### 关联

本文 **RULE-2**（与 router 模板纪律对齐）。

---

## SM40-17 — 端口液体检测和提示

> 飞书章节「十六」。

### 原理

按 `scheme` 选择 SUBPMIC USB_ID / GPIO / WAS4783 等路径做进水检测并轮询上报。

### 底软客制化

1. **文件**：`${charge_overlay}/tc_charger.dtsi` — `&odm`：`tc_audio` 引用 `water_detect`；`water_detect` 节点 `compatible`、`scheme`、`polling_interval`（`bootmode` 新栈是否保留见 bridge）。
2. **器件 dtsi**（如 `&hl1280`）：`high_precision`、`water_set_Resistance` 等。
3. **KO** — `${ko_order_table}`：`tc_water_detect.ko`、`tc_audio.ko`（路径以 `${kdm_root}` 为准）。
4. **取消**：删节点与 KO 行。

### 关联

`transsion-charger-dtsi-driver-bridge`（`water_detect` scheme 映射）。

---

## SM40-18 — 高温不报百

> 飞书章节「十七」。

### 原理

高温低 CV 时若仍报 100% 与可充入能量不一致；驱动在条件满足时锁定 UI SOC 上报，可用 `disable_high_temp_lock_uisoc` 关闭该行为。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi` — `&charger`：`single_batt_level_*` 宽温/常规电池 CV+EOC 段（文档示例 level 7/10/11/13 等）。
- **显式关闭专项**：同节点 `disable_high_temp_lock_uisoc;`（文档「取消方法」）。
- **详述**：`transsion-batt-high-temp-low-cv-eoc`。

---

## SM40-19 — AI 智能充电保护

> 飞书章节「十八」。

### 原理

上层 AI 引擎下发停充/续充；底层执行停充。

### 底软客制化

- **默认导入**；**sysfs**（以实机为准）：`/sys/devices/platform/charger/tran_aichg_disable_charger`（`1` 停充 / `0` 恢复）。
- **上层属性**：`ro.tr_battery.ai_charging_event_track.feature.support`（CMO/属性链）。
- **说明**：文档「取消方法：无」— 不建议随意移除内核接口。

---

## SM40-20 — 自定义充电保护

> 飞书章节「十九」。

### 原理

上层通用停充指令，底层执行停充（与 AI 停充类似）。

### 底软客制化

- **sysfs**：`/sys/devices/platform/charger/tran_custom_disable_charger`（`1` 停充 / `0` 恢复，路径以实机为准）。
- **dtsi**：文档未要求额外属性；默认基线已支持。

---

## SM40-21 — 充电 Trancare 埋点

> 飞书章节「二十」。

### 原理

汇总充电数据上报云端 Trancare。

### 底软客制化

- **文件**：`${kdm_root}` 下 `drivers/power/supply/transsion/tc_trancare.c`（以树内路径为准）
- **修改**：在 `tc_trancare_chg_array[]` 增加属性枚举；在 `tc_chg_trancare_data_get()` 增加 `case` 取数逻辑。
- **验证**：按文档打开 log，搜 `tc_chg_trancare_send_data`。

---

## SM40-22 — 云控（CloudEngine）

> 飞书章节「二十一」。

### 原理

云端下发配置；内核注册 `register_cloudengine_notifier`，回调内更新充电相关开关。

### 底软客制化

1. 申请云控 ID（飞书表格链接见原文）。
2. **`charger_cloud_engine_init()`**：调用 `register_cloudengine_notifier(enhance_charger_id, ...)`。
3. **`charger_cloud_engine_callback_func()`**：按 `id` 匹配执行如 `enhance_charger_cloud_engine_update_switch()`。
4. **取消**：注释 `register_cloudengine_notifier` 段。

---

## SM40-23 — 电池信息显示（欧盟加密电池）

> 飞书章节「二十二」（原文「底软客制化」为空，待 owner 补齐）。

### 原理

面向欧盟加密电池的信息展示与认证（具体链路待业务文档）。

### 底软客制化

- **状态**：飞书该节导入/取消/验证未填；合入前向 **EU 电池接口 owner** 索取涉及 `${charge_overlay}/tc_charger.dtsi`、`bat_setting/*battery_prop*.dtsi`、`${tran_projectconfig}`、Framework 的完整文件清单与属性表。
- **纪律**：路径一律用 `${project_full}` / `${mtk_platform_lower}` 拼接，不写死单板名。

---

## SM40-24 — 单双电芯兼容

> 飞书章节「二十三」。

### 原理

依电池 ID 区分单/双电芯；容量与 PE5 限流表不同。

### 底软客制化

1. **文件**：`${charge_overlay}/bat_setting/*battery_prop*.dtsi`（文件名随平台，如 `${mtk_platform_lower}_battery_prop.dtsi`）— `&mtk_gauge`：`tran_Q_diff` 等。
2. **文件**：`${charge_overlay}/tc_pe50.dtsi` — `&pe5`：`support_multi_bat_parameter;` 与 `bat0_*` / `bat3_*` 等限流表。
3. **取消**：注释 `support_multi_bat_parameter` 并删除多供表。

---

## SM40-25 — 低功率充电增强

> 飞书章节「二十四」。文档限制：导入项目需 >33W；18W 项目不做；测试以 35℃ 环温对比为准。

### 原理

对 ≤18W 场景放宽 PID 目标温度，用更高温升换更快充电。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi` — `&charger`：`support_enhance_mode;`
- **同文件或 pid fragment**：`pid_chg` 节点增加/对齐 `target_temp_array_enhance` 与常规 `target_temp_array`。
- **关闭**：注释 `support_enhance_mode` 并移除/对齐 enhance 温度表。
- **sysfs**：`/sys/devices/platform/charger/support_enhance_mode`（调试验证）。

---

## SM40-26 — 温控充电（已作废）

> 飞书章节「二十五」：专项已作废，仅 SCM 记录。

### 原理

历史「温控充电」能力；不再对新项目导入。

### 底软客制化

- **动作**：新方案 **不配置** 相关 dtsi/KO；老树残留则在升级清单中删除并标注「不支持」。
- **无新增文件**。

---

## SM40-27 — 无线充电功率（充电动画）

> 飞书章节「二十六」。文档：**底软无工作量**。

### 底软客制化

- **配置属性**：`ro.tr_charging.animation_wireless_power`
- **落地位置**：随项目 CMO / `device/*/device.mk` / `product` overlay 拼接，**非单一固定文件**；在 `${AOSP_ROOT}` 内以 `${project_full}` 为关键字检索 `animation_wireless` / `tr_charging` 注入链。
- **底软 dtsi**：无。

---

## SM40-28 — 无线反向充电开关与能力

> 合并飞书章节「二十七」「二十八」（原文说明二者重复、后续删一条）。

### 底软客制化

- **配置属性**：`ro.tr_battery.wireless_reverse_charge.support`
- **落地位置**：CMO / 产品属性注入链；在 `vendor/transsion/projects/${project_full}/` 及关联 `*.mk` 检索拼接点。
- **底软 dtsi**：文档写明无。

---

## SM40-29 — 充电功率（有线充电动画）

> 飞书章节「二十九」。底软无 dtsi。

### 底软客制化

- **配置属性**：`ro.tr_charging.animation_wire_power`
- **落地**：产品/CMO 属性链；以 `${project_full}` 在 `vendor/transsion/projects/`、`device/` 下检索。

---

## SM40-30 — 充电动画（总开关）

> 飞书章节「三十」。底软无 dtsi。

### 底软客制化

- **配置属性**：`ro.tr_charging.animation.support`
- **落地**：产品/CMO；与 **SM40-16（KPOC）** 的 LK/资源路径解耦，勿混为同一文件修改。

---

## SM40-31 — 过压保护提示

> 飞书章节「三十一」。

### 原理

输入电压超安全门限切断充电并上报，上层弹「充电电压过高」类提示。

### 底软客制化

- **文件**：`${charge_overlay}/tc_charger.dtsi` — **节点**：`&charger`
- **属性**：`charger_voltage_ovp = <...>;` **四项**：5V 普通、仅 SWCHG（如 18W）、CP/PE5 有线、无线 PE5；单位以 binding（文档为 µV 量级示例）。

---

## SM40-32 — 无线磁吸充电宝图标

> 飞书章节「三十二」。文档：基线已集成，底软无工作量。

### 底软客制化

- **默认**：无需新增 dtsi。
- **若需调参**：在 `${charge_overlay}/` 下无线相关 fragment（`wireless_*` / `wls_*`，以项目为准）与无线 owner 文档对齐上报与图标映射。

---

## SM40-33 — 无线磁吸风扇充电动画

> 飞书章节「三十三」。一般基线已集成。

### 底软客制化

- **配置属性**：`ro.tr_game.magnetic_fan.support`（CMO/产品属性链检索）。
- **联调**：若同项目开启 **无线旁路 / 磁吸风扇**（见上文 **SM40-11**），核对 `wireless_manager` 与无线固件上报一致性。

### 关联

`transsion-wireless-bypass-fan`。
